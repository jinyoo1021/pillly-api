from fastapi import APIRouter, Depends, Header, Request, HTTPException
from app.schemas.notification import DeviceTokenRequest, NotifyWebhookRequest
from app.services.notification_service import NotificationService
from app.core.security import get_current_user, verify_qstash_signature

router = APIRouter()
notification_service = NotificationService()


@router.post("/token")
async def register_device_token(
        req: DeviceTokenRequest,
        user=Depends(get_current_user),
):
    """Register or update device FCM/APNs token"""
    return notification_service.register_token(user.id, req.token, req.platform)


@router.post("/notify")
async def receive_notify_webhook(
        request: Request,
        req: NotifyWebhookRequest,
):
    """
    QStash webhook endpoint — internal use only
    Validates HMAC signature before processing
    """
    # Verify QStash signature
    signature = request.headers.get("upstash-signature", "")
    body = await request.body()

    if not verify_qstash_signature(body, signature):
        raise HTTPException(status_code=401, detail="INVALID_SIGNATURE")

    return await notification_service.send_push(req.schedule_id, req.user_id)


@router.get("/log")
async def get_notification_log(user=Depends(get_current_user)):
    """Get notification dispatch history"""
    return notification_service.get_logs(user.id)