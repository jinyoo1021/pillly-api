from fastapi import APIRouter, Depends
from app.services.schedule_service import ScheduleService
from app.core.security import get_current_user

router = APIRouter()
schedule_service = ScheduleService()

@router.get("/today")
async def get_today_schedule(user=Depends(get_current_user)):
    """Get today's medication schedule for the dose status."""
    return schedule_service.get_today(user.id)


