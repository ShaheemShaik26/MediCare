from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FactSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fact_type: str
    value: str
    status: str
    confidence: float
    source_excerpt: str | None = None
    page_number: int | None = None
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


class ReviewRequest(BaseModel):
    status: str = Field(..., pattern="^(accepted|rejected|unreviewed)$")
