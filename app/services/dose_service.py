from datetime import date, datetime, timezone
from fastapi import HTTPException
from app.core.supabase import supabase


class DoseService:

    def confirm(self, schedule_id: str, user_id: str) -> dict:
        """Mark medication as taken"""
        try:
            today = date.today().isoformat()

            # Check for duplicate log
            existing = supabase.table("dose_logs") \
                .select("id") \
                .eq("schedule_id", schedule_id) \
                .eq("log_date", today) \
                .execute()

            if existing.data:
                raise HTTPException(
                    status_code=400,
                    detail="ALREADY_LOGGED",
                )

            result = supabase.table("dose_logs").insert({
                "schedule_id": schedule_id,
                "user_id": user_id,
                "log_date": today,
                "status": "done",
                "taken_at": datetime.now(timezone.utc).isoformat(),
            }).execute()

            return {
                "log_id": result.data[0]["id"],
                "status": "done",
                "taken_at": result.data[0]["taken_at"],
            }

        except HTTPException:
            raise
        except Exception as e:
            print(f"ERROR in confirm: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def skip(self, schedule_id: str, user_id: str) -> dict:
        """Mark medication as skipped"""
        try:
            today = date.today().isoformat()

            # Check for duplicate log
            existing = supabase.table("dose_logs") \
                .select("id") \
                .eq("schedule_id", schedule_id) \
                .eq("log_date", today) \
                .execute()

            if existing.data:
                raise HTTPException(
                    status_code=400,
                    detail="ALREADY_LOGGED",
                )

            result = supabase.table("dose_logs").insert({
                "schedule_id": schedule_id,
                "user_id": user_id,
                "log_date": today,
                "status": "skipped",
            }).execute()

            return {
                "log_id": result.data[0]["id"],
                "status": "skipped",
            }

        except HTTPException:
            raise
        except Exception as e:
            print(f"ERROR in skip: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_logs(self, user_id: str, from_date: str, to_date: str) -> dict:
        """Get dose logs for calendar view"""
        try:
            # Fetch all schedules for user
            medications = supabase.table("medications") \
                .select("id, schedules(id)") \
                .eq("user_id", user_id) \
                .is_("deleted_at", "null") \
                .execute()

            # Count total schedules per day
            schedule_count = sum(
                len(med["schedules"])
                for med in medications.data
            )

            if schedule_count == 0:
                return {"logs": []}

            # Fetch dose logs in date range
            logs = supabase.table("dose_logs") \
                .select("log_date, status") \
                .eq("user_id", user_id) \
                .gte("log_date", from_date) \
                .lte("log_date", to_date) \
                .execute()

            # Group by date
            date_map: dict = {}
            for log in logs.data:
                d = log["log_date"]
                if d not in date_map:
                    date_map[d] = {"done": 0, "total": schedule_count}
                if log["status"] == "done":
                    date_map[d]["done"] += 1

            # Build response
            result = []
            for d, counts in sorted(date_map.items()):
                total = counts["total"]
                done = counts["done"]
                rate = round(done / total * 100) if total > 0 else 0

                if rate == 100:
                    grade = "green"
                elif rate > 0:
                    grade = "yellow"
                else:
                    grade = "red"

                result.append({
                    "date": d,
                    "total": total,
                    "done": done,
                    "rate": rate,
                    "grade": grade,
                })

            return {"logs": result}

        except Exception as e:
            print(f"ERROR in get_logs: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_stats(self, user_id: str, period: str) -> dict:
        """Get dose statistics by period (week or month)"""
        try:
            from datetime import timedelta

            today = date.today()
            if period == "week":
                from_date = (today - timedelta(days=7)).isoformat()
            else:
                from_date = (today - timedelta(days=30)).isoformat()

            to_date = today.isoformat()

            # Fetch medications with schedules
            medications = supabase.table("medications") \
                .select("id, name, color_tag, schedules(id)") \
                .eq("user_id", user_id) \
                .eq("is_active", True) \
                .is_("deleted_at", "null") \
                .execute()

            if not medications.data:
                return {
                    "period": period,
                    "overall_rate": 0,
                    "by_medication": [],
                }

            # Fetch dose logs in range
            logs = supabase.table("dose_logs") \
                .select("schedule_id, status") \
                .eq("user_id", user_id) \
                .gte("log_date", from_date) \
                .lte("log_date", to_date) \
                .execute()

            # Build schedule → medication map
            schedule_med_map = {}
            for med in medications.data:
                for s in med["schedules"]:
                    schedule_med_map[s["id"]] = med["id"]

            # Count done logs per medication
            med_done_map: dict = {}
            med_total_map: dict = {}

            days = 7 if period == "week" else 30

            for med in medications.data:
                med_id = med["id"]
                med_total_map[med_id] = len(med["schedules"]) * days
                med_done_map[med_id] = 0

            for log in logs.data:
                if log["status"] == "done":
                    med_id = schedule_med_map.get(log["schedule_id"])
                    if med_id:
                        med_done_map[med_id] = med_done_map.get(med_id, 0) + 1

            # Build by_medication stats
            by_medication = []
            total_done = 0
            total_possible = 0

            for med in medications.data:
                med_id = med["id"]
                done = med_done_map.get(med_id, 0)
                total = med_total_map.get(med_id, 1)
                rate = round(done / total * 100) if total > 0 else 0

                total_done += done
                total_possible += total

                by_medication.append({
                    "medication_name": med["name"],
                    "color_tag": med["color_tag"],
                    "rate": rate,
                })

            overall_rate = round(total_done / total_possible * 100) \
                if total_possible > 0 else 0

            return {
                "period": period,
                "overall_rate": overall_rate,
                "by_medication": by_medication,
            }

        except Exception as e:
            print(f"ERROR in get_stats: {e}")
            raise HTTPException(status_code=500, detail=str(e))