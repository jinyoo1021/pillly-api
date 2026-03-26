from pydantic import BaseModel
from typing import Optional

# Dose request schemas

class DoseConfirmRequest(BaseModel):
    schedule_id: str

class DoseSkipRequest(BaseModel):
    schedule_id: str


# Schedule response schemas

# class ScheduleDose(BaseModel):
#     schedule_id: str
#     medication_name: str
#     scheduled_time: str
#     color_tag: str
#     status: str
#     taken_at: Optional[str] = None
#
# class TodayScheduleResponse(BaseModel):
#     date: str
#     total: int
#     done: int
#     rate: int
#     itmes: list[ScheduleItem]

class DoseLogItem(BaseModel):
    date: str
    total: int
    done: int
    rate: int
    grade: str          # "green", "yellow", "red"

class DoseStatItem(BaseModel):
    medication_name: str
    color_tag: str
    rate: int

class DoseStateResponse(BaseModel):
    period: str
    overall_rate: int
    by_medication: list[DoseStatItem]




