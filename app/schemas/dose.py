from pydantic import BaseModel
from typing import Optional

# Dose request schemas

class DoseConfrimRequest(BaseModel):
    schedule_id: str

class DoseSkipRequest(BaseModel):
    schedule_id: str


# Schedule response schemas

class ScheduleDose(BaseModel):
    schedule_id: str
    medication_name: str
    scheduled_time: str
    color_tag: str
    status: str
    taken_at: Optional[str] = None

class TodayScheduleResponse(BaseModel):
    date: str
    total: int
    done: int
    rate: int
    itmes: list[ScheduleItem]

