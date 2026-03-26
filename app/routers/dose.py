from fastapi import APIRouter, Depends, Query
from app.schemas.dose import DoseConfirmRequest, DoseSkipRequest
from app.services.dose_service import DoseService
from app.core.security import get_current_user

router = APIRouter()
dose_service = DoseService()


@router.post("/confirm", status_code=201)
async def confirm_dose(
        req: DoseConfirmRequest,
        user=Depends(get_current_user),
):
    """Mark medication as taken"""
    return dose_service.confirm(req.schedule_id, user.id)


@router.post("/skip", status_code=201)
async def skip_dose(
        req: DoseSkipRequest,
        user=Depends(get_current_user),
):
    """Mark medication as skipped"""
    return dose_service.skip(req.schedule_id, user.id)


@router.get("/logs")
async def get_dose_logs(
        from_date: str = Query(..., alias="from"),
        to_date: str = Query(..., alias="to"),
        user=Depends(get_current_user),
):
    """Get dose logs for calendar view"""
    return dose_service.get_logs(user.id, from_date, to_date)


@router.get("/stats")
async def get_dose_stats(
        period: str = Query("week", pattern="^(week|month)$"),
        user=Depends(get_current_user),
):
    """Get dose statistics by period"""
    return dose_service.get_stats(user.id, period)