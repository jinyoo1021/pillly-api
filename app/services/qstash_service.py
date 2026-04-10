import httpx
import json
from app.core.config import settings
from app.core.supabase import supabase


QSTASH_BASE_URL = "https://qstash.upstash.io/v2"



class QStashService:
    """Manages QStash scheduled webhooks for medication reminders"""

    def __init__(self):
        self._headers = {
            "Authorization": f"Bearer {settings.QSTASH_TOKEN}",
            "Content-Type": "application/json",
        }
        # Webhook endpoint that QStash will call at scheduled times
        self._callback_url = f"{settings.API_URL}/v1/notifications/notify"

    # ── Public API ───────────────────────────────────────

    async def sync_schedules(self, medication_id: str, user_id: str) -> dict:
        """
        Sync all QStash schedules for a medication.
        Called on medication create / update.
        Deletes old schedules, creates new ones for all active schedules.
        """
        # Remove existing QStash schedules for this medication
        await self._delete_schedules_for_medication(medication_id)

        # Fetch active schedules from DB
        result = supabase.table("schedules") \
            .select("id, scheduled_time, cycle_type, cycle_value, is_active") \
            .eq("medication_id", medication_id) \
            .eq("is_active", True) \
            .execute()

        if not result.data:
            return {"synced": 0}

        # Create a QStash schedule for each active schedule
        created = 0
        for schedule in result.data:
            cron = self._build_cron(schedule)
            if cron is None:
                continue

            qstash_id = await self._create_schedule(
                schedule_id=schedule["id"],
                user_id=user_id,
                cron=cron,
            )

            if qstash_id:
                # Store QStash schedule ID in DB for future management
                supabase.table("schedules") \
                    .update({"qstash_schedule_id": qstash_id}) \
                    .eq("id", schedule["id"]) \
                    .execute()
                created += 1

        return {"synced": created}

    async def delete_all_for_medication(self, medication_id: str) -> None:
        """Remove all QStash schedules for a medication (on delete/toggle off)"""
        await self._delete_schedules_for_medication(medication_id)

    # ── QStash API calls ─────────────────────────────────

    async def _create_schedule(
            self, schedule_id: str, user_id: str, cron: str
    ) -> str | None:
        """Create a single QStash cron schedule, return schedule ID"""
        payload = {
            "schedule_id": schedule_id,
            "user_id": user_id,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{QSTASH_BASE_URL}/schedules/{self._callback_url}",
                headers={
                    **self._headers,
                    "Upstash-Cron": cron,
                    "Upstash-Retries": "3",
                },
                json=payload,
            )

            if resp.status_code == 201:
                data = resp.json()
                qstash_id = data.get("scheduleId")
                print(f"QStash schedule created: {qstash_id} | cron: {cron}")
                return qstash_id
            else:
                print(f"QStash create FAILED: {resp.status_code} {resp.text}")
                return None

    async def _delete_schedule(self, qstash_schedule_id: str) -> bool:
        """Delete a single QStash schedule by its ID"""
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{QSTASH_BASE_URL}/schedules/{qstash_schedule_id}",
                headers=self._headers,
            )

            if resp.status_code in (200, 204):
                print(f"QStash schedule deleted: {qstash_schedule_id}")
                return True
            else:
                print(f"QStash delete FAILED: {resp.status_code} {resp.text}")
                return False

    async def _delete_schedules_for_medication(self, medication_id: str) -> None:
        """Delete all QStash schedules linked to a medication"""
        result = supabase.table("schedules") \
            .select("id, qstash_schedule_id") \
            .eq("medication_id", medication_id) \
            .not_.is_("qstash_schedule_id", "null") \
            .execute()

        for schedule in result.data or []:
            qstash_id = schedule.get("qstash_schedule_id")
            if qstash_id:
                await self._delete_schedule(qstash_id)
                # Clear stored ID
                supabase.table("schedules") \
                    .update({"qstash_schedule_id": None}) \
                    .eq("id", schedule["id"]) \
                    .execute()

    # ── Cron expression builder ──────────────────────────

    def _build_cron(self, schedule: dict) -> str | None:
        """
        Convert schedule to cron expression.
        scheduled_time format: "HH:MM:SS" or "HH:MM"
        Returns: "MM HH * * *" (daily), "MM HH * * 1,3,5" (weekly), etc.
        KST = UTC + 9, so subtract 9 hours.
        """
        time_str = schedule["scheduled_time"]
        parts = time_str.split(":")
        hour_kst = int(parts[0])
        minute = int(parts[1])

        # Convert KST to UTC (KST - 9)
        hour_utc = (hour_kst - 9) % 24

        cycle_type = schedule.get("cycle_type", "daily")
        cycle_value = schedule.get("cycle_value")

        if cycle_type == "daily":
            # Every day at HH:MM
            return f"{minute} {hour_utc} * * *"

        elif cycle_type == "weekly":
            # Specific weekdays — cycle_value: {"weekdays": [1,3,5]}
            # Python isoweekday: 1=Mon..7=Sun → cron: 0=Sun..6=Sat
            weekdays = []
            if isinstance(cycle_value, dict):
                weekdays = cycle_value.get("weekdays", [])

            if not weekdays:
                return f"{minute} {hour_utc} * * *"

            # Convert ISO weekday (1=Mon,7=Sun) to cron (0=Sun,6=Sat)
            cron_days = []
            for d in weekdays:
                cron_days.append(d % 7)  # 1→1, 2→2, ..., 7→0
                # If KST hour < 9, UTC date is previous day
                if hour_kst < 9:
                    cron_day = (cron_day - 1) % 7
                cron_days.append(cron_day)

            days_str = ",".join(str(d) for d in sorted(cron_days))
            return f"{minute} {hour_utc} * * {days_str}"

        elif cycle_type == "interval":
            # Interval-based: QStash doesn't support "every N days" natively.
            # Use daily cron + server-side filtering in the webhook handler.
            return f"{minute} {hour_utc} * * *"

        return None