from pydantic import BaseModel
from typing import Optional

# Schedule schemas

class ScheduleCreate(BaseModel):
    scheduled_time: str
    cycle_type: str
    cycle_value: Optional[dict | list] = None

class ScheduleResponse(BaseModel):
    id: str
    scheduled_time: str
    cycle_type: str
    cycle_value: Optional[dict | list] = None
    is_active: bool

# Medication schemas

class MedicationCreate(BaseModel):
    name: str
    dosage: Optional[str] = None
    color_tag: Optional[str] = "#1D9E75"
    memo: Optional[str] = None
    schedules: list[ScheduleCreate]

class MedicationUpdate(BaseModel):
    name: Optional[str] = None
    dosage: Optional[str] = None
    color_tag: Optional[str] = None
    memo: Optional[str] = None

class MedicationResponse(BaseModel):
    id: str
    name: str
    dosage: Optional[str] = None
    color_tag: str
    memo: Optional[str] = None
    is_active: bool
    schedules: list[ScheduleResponse] = []
