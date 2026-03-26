from fastapi import HTTPException, Request
from datetime import datetime, timezone
from app.core.supabase import supabase
from app.core.config import settings
from app.core.security import verify_qstash_signature
import httpx

class NotificationService:

    def register_token(self, user_id: str, token: str, platform: str) -> dict:
        """Register or Update device FCM/APNs token"""
        try:
            # Upsert device token
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
                .select("id, scheduled_time, medication_id") \
                .eq("id", schedule_id) \
                .single() \
                .execute()

            if not schedule.data:
                raise HTTPException(status_code=404, detail="SCHEDULE_NOT_FOUND")

            # Fetch medication name
            medication = supabase.table("medications") \
                .select("name") \
                .eq("id", schedule.data["medication_id"]) \
                .single() \
                .execute()


            medication_name = medication.data["name"] if medication.data else "Unknown"

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
                # Fetch medication name per log
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
        """Send Android push via FCM"""
        # Will be implemented when Firebase credentials are available
        # for now,
        print(f"FCM send to {token[:20]}... | {medication_name} (schedule {schedule_id})")

    async def _send_apns(self, token: str, schedule_id: str, medication_name: str) -> None:
        """Send iOS push via APNs"""
        # Will be implemented when APNs credentials are available
        # for now,
        print(f"APNs send to {token[:20]}... | {medication_name} (schedule {schedule_id})")

