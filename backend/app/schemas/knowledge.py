from pydantic import BaseModel, Field


class HealthTopicQuestion(BaseModel):
    query: str = Field(..., min_length=2, max_length=120)


class HealthTopic(BaseModel):
    title: str
    summary: str
    url: str
    source: str
