from pydantic import BaseModel
from typing import Optional

# Request schemas
class DeviceTokenRequest(BaseModel):
    token: str
    platform: str       # "ios" or "android"

class NotifyWebhookRequest(BaseModel):
    schedule_id: str
    user_id: str


# Response schemas

class NotificationLogItem(BaseModel):
    medication_name: str
    sent_at: str
    status: str
    snooze_count: int

