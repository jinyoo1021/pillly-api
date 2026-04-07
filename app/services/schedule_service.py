from datetime import date
from fastapi import HTTPException
from app.core.supabase import supabase


class ScheduleService:

    def get_today(self, user_id: str) -> dict:
        """Get today's medication schedule with dose status"""
        try:
            today = date.today().isoformat()
            today_weekday = date.today().isoweekday()

            # Fetch all active medications for the user
            medications = supabase.table("medications") \
                .select("id, name, color_tag, schedules(id, scheduled_time, cycle_type, cycle_value, is_active)") \
                .eq("user_id", user_id) \
                .eq("is_active", True) \
                .is_("deleted_at", "null") \
                .execute()

            if not medications.data:
                return {
                    "date": today,
                    "total": 0,
                    "done": 0,
                    "rate": 0,
                    "items": [],
                }

            # Flatten all schedules
            all_schedules = []
            for med in medications.data:
                for s in med.get("schedules", []):

                    # Skip inactive schedules
                    if not s.get("is_active", True):
                        continue

                    cycle_type = s.get("cycle_type", "daily")
                    cycle_value = s.get("cycle_value")

                    # Daily: always include
                    if cycle_type == "daily":
                        pass
                    # Weekly: include only if today matches selected weekdays
                    elif cycle_type == "weekly":
                        weekdays = cycle_value.get("weekdays", []) if isinstance(cycle_value, dict) else []
                        if today_weekday not in weekdays:
                            continue
                    # Interval: include only if today matches the interval
                    elif cycle_type == "interval":
                        interval = cycle_value.get("days", 1) if isinstance(cycle_value, dict) else 1
                        ref_date_str = cycle_value.get("start_date") if isinstance(cycle_value, dict) else None
                        if ref_date_str:
                            from datetime import datetime
                            ref_date = datetime.strptime(ref_date_str, "%Y-%m-%d").date()
                            if (date.today() - ref_date).days % interval != 0:
                                continue

                    all_schedules.append({
                        "schedule_id": s["id"],
                        "scheduled_time": s["scheduled_time"],
                        "medication_name": med["name"],
                        "color_tag": med["color_tag"],
                    })

            if not all_schedules:
                return {
                    "date": today,
                    "total": 0,
                    "done": 0,
                    "rate": 0,
                    "items": [],
                }

            # Fetch today's dose logs for this user
            logs = supabase.table("dose_logs") \
                .select("schedule_id, status, taken_at") \
                .eq("user_id", user_id) \
                .eq("log_date", today) \
                .execute()

            # Build log map for quick lookup
            log_map = {log["schedule_id"]: log for log in logs.data}

            # Build response items
            items = []
            done_count = 0

            for s in all_schedules:
                log = log_map.get(s["schedule_id"])
                status = log["status"] if log else "pending"
                if status == "done":
                    done_count += 1

                items.append({
                    "schedule_id": s["schedule_id"],
                    "medication_name": s["medication_name"],
                    "scheduled_time": s["scheduled_time"][:5],  # Show only HH:MM
                    "color_tag": s["color_tag"],
                    "status": status,
                    "taken_at": log["taken_at"] if log else None,
                })

            # Sort by scheduled time
            items.sort(key=lambda x: x["scheduled_time"])

            total = len(items)
            rate = round(done_count / total * 100) if total > 0 else 0

            return {
                "date": today,
                "total": total,
                "done": done_count,
                "rate": rate,
                "items": items,
            }

        except Exception as e:
            print(f"ERROR in get_today: {e}")
            raise HTTPException(status_code=500, detail=str(e))