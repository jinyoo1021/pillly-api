from fastapi import APIRouter, Depends
from app.schemas.medication import MedicationCreate, MedicationUpdate
from app.services.medication_service import MedicationService
from app.core.security import get_current_user

router = APIRouter()
medication_service = MedicationService()

@router.get("")
async def get_medication(user=Depends(get_current_user)):
    """Get all medication for current user"""
    return {"medications": medication_service.get_all(user.id)}

@router.post("", status_code=201)
async def create_medication(
        req: MedicationCreate,
        user=Depends(get_current_user),
):
    """Create a new medication with schedules and register QStash crons"""
    return await medication_service.create(user.id, req)

@router.patch("/{medication_id}/toggle")
async def toggle_medication(
        medication_id: str,
        user=Depends(get_current_user),
):
    """Toggle medication active status and sync QStash schedules"""
    return await medication_service.toggle(medication_id, user.id)

@router.patch("/{medication_id}")
async def update_medication(
        medication_id: str,
        req: MedicationUpdate,
        user=Depends(get_current_user),
):
    """Update medication info and re-sync QStash schedules"""
    return await medication_service.update(medication_id, user.id, req)

@router.delete("/{medication_id}", status_code=200)
async def delete_medication(
        medication_id: str,
        user=Depends(get_current_user),
):
    """Soft delete medication and remove QStash schedules"""
    await medication_service.delete(medication_id, user.id)
    return {"message": "Successfully deleted"}