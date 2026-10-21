from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LifestyleProfileUpdate(BaseModel):
    activity_frequency: Literal["rarely", "1-2 days/week", "3-4 days/week", "5+ days/week"] | None = None
    diet_notes: str | None = Field(default=None, max_length=1000)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    tobacco_use: Literal["never", "former", "current", "prefer_not_to_say"] | None = None
    alcohol_frequency: Literal["never", "occasionally", "weekly", "daily", "prefer_not_to_say"] | None = None
    notes: str | None = Field(default=None, max_length=1000)


class LifestyleProfileSchema(LifestyleProfileUpdate):
    model_config = ConfigDict(from_attributes=True)

    updated_at: datetime
