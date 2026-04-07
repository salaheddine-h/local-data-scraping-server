from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class TaskCreate(BaseModel):
    """Payload for submitting a new scraping task."""

    url: HttpUrl
    source: str = Field(default="api", max_length=100)
    keywords: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    request_timeout: int = Field(default=15, ge=1, le=120)


class TaskResponse(BaseModel):
    """Response returned when a task is successfully queued."""

    status: str
    queue: str
    task_id: str


class RedisStatus(BaseModel):
    """Health information of the Redis connection."""

    status: str
    scrape_queue_length: int = 0
    processing_queue_length: int = 0
    error: str | None = None


class StatusResponse(BaseModel):
    """Overall system health status."""

    service: str
    timestamp: str
    overall: str
    redis: RedisStatus
