from fastapi import APIRouter, HTTPException
from redis.exceptions import RedisError

from schemas import StatusResponse, TaskCreate, TaskResponse
from services.redis_queue import check_redis_health, enqueue_task

router = APIRouter()


@router.post("/task", response_model=TaskResponse, status_code=202)
def create_task(task: TaskCreate):
    """
    Submits a new scraping task to the queue.
    """
    try:
        result = enqueue_task(
            url=str(task.url),
            source=task.source,
            keywords=task.keywords,
            metadata=task.metadata,
            request_timeout=task.request_timeout,
        )
        return TaskResponse(**result)
    except RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Task queue unavailable: {str(exc)}",
        ) from exc


@router.get("/status", response_model=StatusResponse)
def get_status():
    """
    Check the overall health of the API and its connection to Redis.
    """
    from datetime import datetime, timezone

    redis_health = check_redis_health()
    overall_status = "ok" if redis_health["status"] == "ok" else "degraded"

    return StatusResponse(
        service="api",
        timestamp=datetime.now(timezone.utc).isoformat(),
        overall=overall_status,
        redis=redis_health,
    )
