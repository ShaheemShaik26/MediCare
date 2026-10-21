from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FactSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    fact_type: str
    value: str
    status: str
    confidence: float
    source_excerpt: str | None = None
    page_number: int | None = None
    event_date: date | None = None
    numeric_value: float | None = None
    unit: str | None = None
    created_at: datetime


class DocumentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    content_type: str
    status: str
    preview_text: str | None = None
    document_type: str | None = None
    document_date: str | None = None
    provider_name: str | None = None
    uploaded_at: datetime


class DocumentExtractionResponse(BaseModel):
    document_id: int
    extracted_fact_count: int
    updated_fact_count: int
    status: str


class ReviewRequest(BaseModel):
    status: str = Field(..., pattern="^(accepted|rejected|unreviewed)$")
    fact_type: str | None = Field(default=None, min_length=1, max_length=64)
    value: str | None = Field(default=None, min_length=1, max_length=2000)
    event_date: date | None = None
    clear_event_date: bool = False


class ManualFactCreate(BaseModel):
    fact_type: Literal[
        "diagnosis",
        "symptom",
        "medication",
        "allergy",
        "lab",
        "procedure",
        "medical_event",
        "provider",
        "lifestyle_activity",
        "lifestyle_sleep",
        "lifestyle_diet",
        "lifestyle_tobacco",
        "lifestyle_alcohol",
    ]
    value: str = Field(..., min_length=1, max_length=2000)
    event_date: date | None = None
    page_number: int | None = Field(default=None, ge=1, le=100)

    @field_validator("value")
    @classmethod
    def require_nonblank_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("A health detail is required.")
        return normalized


class RecordsQuestion(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


class RecordCitation(BaseModel):
    document_id: int
    file_name: str
    page_number: int | None
    event_date: date | None
    excerpt: str | None


class RecordsAnswer(BaseModel):
    answer: str
    insufficient_evidence: bool
    possible_conflict: bool
    citations: list[RecordCitation]
