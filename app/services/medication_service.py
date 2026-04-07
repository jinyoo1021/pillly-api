from fastapi import HTTPException
from app.core.supabase import supabase
from app.schemas.medication import MedicationCreate, MedicationUpdate


class MedicationService:

    def get_all(self, user_id: str) -> list:
        """Get all active medication with scheludes for a user"""
        response = supabase.table("medications") \
            .select("*, schedules(*)") \
            .eq("user_id", user_id) \
            .is_("deleted_at", "null") \
            .order("created_at", desc=True) \
            .execute()

        return response.data

    def create(self, user_id: str, req: MedicationCreate) -> dict:
        """Create a new medication with schedules"""
        try:
            print(f"Creating medication for user_id: {user_id}")\

            #Check if user exists in public.users
            user_check = supabase.table("users") \
                .select("id") \
                .eq("id", user_id) \
                .execute()
            print(f"User in public.users: {user_check.data}")

            # Check for duplicate name
            existing = supabase.table("medications") \
                .select("id") \
                .eq("user_id", user_id) \
                .eq("name", req.name) \
                .is_("deleted_at", "null") \
                .execute()

            if existing.data:
                raise HTTPException(
                    status_code=400,
                    detail="DUPLICATE_MEDICATION_NAME",
                )

            # Create medication
            med = supabase.table("medications").insert({
                "user_id": user_id,
                "name": req.name,
                "dosage": req.dosage,
                "color_tag": req.color_tag or "#1D9E75",
                "memo": req.memo,
            }).execute()

            medication_id = med.data[0]["id"]

            # Create schedules
            schedules = [
                {
                    "medication_id": medication_id,
                    "scheduled_time": s.scheduled_time,
                    "cycle_type": s.cycle_type,
                    "cycle_value": s.cycle_value,
                }
                for s in req.schedules
            ]
            supabase.table("schedules").insert(schedules).execute()

            return {
                "id": medication_id,
                "name": req.name,
                "created_at": med.data[0]["created_at"],
            }
        except Exception as e:
            print(f"ERROR in create medication: {e}") # print error for debugging
            raise HTTPException(status_code=500, detail=str(e))


    def update(self, medication_id: str, user_id: str, req: MedicationUpdate) -> dict:
        """Update medication info and schedules"""
        self._verify_owner(medication_id, user_id)

        # Update medications table, excluding schedules field
        med_payload = {
            k: v for k, v in req.model_dump(exclude={"schedules"}).items()
            if v is not None
        }
        if med_payload:
            supabase.table("medications") \
                .update(med_payload) \
                .eq("id", medication_id) \
                .execute()

        # Soft delete existing schedules and insert new ones
        # Hard delete is not possible due to FK constraint from dose_logs
        if req.schedules is not None:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()

            # Soft delete active schedules
            supabase.table("schedules") \
                .update({"is_active": False}) \
                .eq("medication_id", medication_id) \
                .eq("is_active", True) \
                .execute()

            # Insert new schedules
            new_schedules = [
                {
                    "medication_id": medication_id,
                    "scheduled_time": s.scheduled_time,
                    "cycle_type": s.cycle_type,
                    "cycle_value": s.cycle_value,
                }
                for s in req.schedules
            ]
            supabase.table("schedules").insert(new_schedules).execute()

        # Return updated medication with schedules
        result = supabase.table("medications") \
            .select("*, schedules!inner(*)") \
            .eq("id", medication_id) \
            .single() \
            .execute()

        data = result.data
        data["schedules"] = [s for s in data.get("schedules", []) if s.get("is_active", True)]
        return data

    def delete(self, medication_id: str, user_id: str) -> None :
        """Soft delete medication and its schedules"""
        self._verify_owner(medication_id, user_id)

        from datetime import datetime, timezone
        supabase.table("medications") \
            .update({"deleted_at": datetime.now(timezone.utc).isoformat()}) \
            .eq("id", medication_id) \
            .execute()

    def toggle(self, medication_id: str, user_id: str) -> dict:
        """Toggle medication active/incative"""
        self._verify_owner(medication_id, user_id)

        # G
        current = supabase.table("medications") \
            .select("is_active") \
            .eq("id", medication_id) \
            .single() \
            .execute()

        new_state = not current.data["is_active"]

        result = supabase.table("medications") \
            .update({"is_active": new_state}) \
            .eq("id", medication_id) \
            .execute()

        return {"id": medication_id, "is_active": new_state}

    def _verify_owner(self, medication_id: str, user_id: str) -> None:
        """Verify the medication belongs to the user"""
        result = supabase.table("medications") \
            .select("id") \
            .eq("id", medication_id) \
            .eq("user_id", user_id) \
            .is_("deleted_at", "null") \
            .execute()

        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="MEDICATION_NOT_FOUND",
            )
