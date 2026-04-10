from fastapi import HTTPException
from datetime import datetime, date, timezone
from app.core.supabase import supabase
from app.core.config import settings
import firebase_admin
from firebase_admin import credentials, messaging

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)


class NotificationService:

    def register_token(self, user_id: str, token: str, platform: str) -> dict:
        """Register or update device FCM/APNs token"""
        try:
            supabase.table("device_tokens").upsert({
                "user_id": user_id,
                "token": token,
                "platform": platform,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="token").execute()

            return {"registered": True}

        except Exception as e:
            print(f"ERROR in register_token: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def send_push(self, schedule_id: str, user_id: str) -> dict:
        """Send push notification via FCM or APNs"""
        try:
            # Fetch schedule + medication info
            schedule = supabase.table("schedules") \
                .select("id, scheduled_time, cycle_type, cycle_value, medication_id") \
                .eq("id", schedule_id) \
                .single() \
                .execute()

            if not schedule.data:
                raise HTTPException(status_code=404, detail="SCHEDULE_NOT_FOUND")

            # ── Interval-type guard ──────────────────────
            # QStash fires daily for interval schedules,
            # so we check here if today is actually a valid day.
            cycle_type = schedule.data.get("cycle_type", "daily")
            cycle_value = schedule.data.get("cycle_value")

            if cycle_type == "interval" and isinstance(cycle_value, dict):
                interval_days = cycle_value.get("days", 1)
                start_date_str = cycle_value.get("start_date")
                if start_date_str and interval_days > 1:
                    start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                    if (date.today() - start).days % interval_days != 0:
                        print(f"Interval skip: not a valid day for schedule {schedule_id}")
                        return {"sent": False, "reason": "INTERVAL_NOT_TODAY"}

            # Fetch medication name
            medication = supabase.table("medications") \
                .select("name, is_active") \
                .eq("id", schedule.data["medication_id"]) \
                .single() \
                .execute()

            if not medication.data or not medication.data.get("is_active", True):
                print(f"Medication inactive or not found for schedule {schedule_id}")
                return {"sent": False, "reason": "MEDICATION_INACTIVE"}

            medication_name = medication.data["name"]

            # Fetch device token
            token_row = supabase.table("device_tokens") \
                .select("token, platform") \
                .eq("user_id", user_id) \
                .execute()

            if not token_row.data:
                print(f"No device token for user {user_id}, skipping notification")
                supabase.table("notification_logs").insert({
                    "schedule_id": schedule_id,
                    "user_id": user_id,
                    "status": "skipped_no_token",
                    "snooze_count": 0,
                }).execute()
                return {"sent": False, "reason": "NO_DEVICE_TOKEN"}

            device = token_row.data[0]

            # Send by platform
            if device["platform"] == "android":
                await self._send_fcm(device["token"], schedule_id, medication_name)
            else:
                await self._send_apns(device["token"], schedule_id, medication_name)

            # Log success
            supabase.table("notification_logs").insert({
                "schedule_id": schedule_id,
                "user_id": user_id,
                "status": "delivered",
                "snooze_count": 0,
            }).execute()

            return {"sent": True, "platform": device["platform"]}

        except HTTPException:
            raise
        except Exception as e:
            print(f"ERROR in send_push: {e}")
            supabase.table("notification_logs").insert({
                "schedule_id": schedule_id,
                "user_id": user_id,
                "status": "failed",
                "snooze_count": 0,
            }).execute()
            raise HTTPException(status_code=500, detail=str(e))

    def get_logs(self, user_id: str) -> dict:
        """Get notification dispatch history for user"""
        try:
            logs = supabase.table("notification_logs") \
                .select("sent_at, status, snooze_count, schedule_id") \
                .eq("user_id", user_id) \
                .order("sent_at", desc=True) \
                .limit(50) \
                .execute()

            if not logs.data:
                return {"logs": []}

            items = []
            for log in logs.data:
                schedule = supabase.table("schedules") \
                    .select("medication_id") \
                    .eq("id", log["schedule_id"]) \
                    .execute()

                med_name = "Unknown"
                if schedule.data:
                    medication = supabase.table("medications") \
                        .select("name") \
                        .eq("id", schedule.data[0]["medication_id"]) \
                        .execute()
                    if medication.data:
                        med_name = medication.data[0]["name"]

                items.append({
                    "medication_name": med_name,
                    "sent_at": log["sent_at"],
                    "status": log["status"],
                    "snooze_count": log["snooze_count"],
                })

            return {"logs": items}

        except Exception as e:
            import traceback
            print(f"ERROR in get_logs: {e}")
            print(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e))

    async def _send_fcm(self, token: str, schedule_id: str, medication_name: str) -> None:
        """Send data-only FCM message for action button support"""
        message = messaging.Message(
            data={
                'schedule_id': schedule_id,
                'log_date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                'medication_name': medication_name,
                'title': '💊 Medication Reminder',
                'body': f'Time to take {medication_name}',
                'type': 'medication_reminder',
            },
            android=messaging.AndroidConfig(
                priority='high',
            ),
            token=token,
        )

        try:
            result = messaging.send(message)
            print(f"FCM sent successfully: {result}")
        except Exception as e:
            print(f"FCM send FAILED: {e}")
            raise

    async def _send_apns(self, token: str, schedule_id: str, medication_name: str) -> None:
        """Send iOS push via APNs (placeholder)"""
        print(f"APNs send to {token[:20]}... | {medication_name} (schedule {schedule_id})")