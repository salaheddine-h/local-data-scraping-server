import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg
import redis
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, HttpUrl


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


configure_logging()
logger = logging.getLogger("api")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app@postgres:5432/local_data")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SCRAPE_QUEUE_NAME = os.getenv("SCRAPE_QUEUE_NAME", "scrape_tasks")
PROCESS_QUEUE_NAME = os.getenv("PROCESS_QUEUE_NAME", "processing_tasks")

app = FastAPI(title="Local Data Platform API", version="0.1.0")


class TaskCreate(BaseModel):
    url: HttpUrl
    source: str = Field(default="manual", max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
    request_timeout: int = Field(default=20, ge=1, le=120)


def get_redis_client() -> redis.Redis:
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


def get_db_connection() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error for %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.post("/task", status_code=202)
def create_task(task: TaskCreate) -> dict[str, Any]:
    task_payload = {
        "task_id": str(uuid.uuid4()),
        "url": str(task.url),
        "source": task.source,
        "metadata": task.metadata,
        "request_timeout": task.request_timeout,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        redis_client = get_redis_client()
        redis_client.rpush(SCRAPE_QUEUE_NAME, json.dumps(task_payload))
    except redis.RedisError as exc:
        logger.exception("Failed to enqueue task")
        raise HTTPException(status_code=503, detail="Task queue unavailable") from exc

    return {
        "status": "queued",
        "queue": SCRAPE_QUEUE_NAME,
        "task": task_payload,
    }


@app.get("/datasets")
def get_datasets(
    limit: int = Query(default=50, ge=1, le=500),
    source: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    query = """
        SELECT
            id,
            task_id,
            source,
            url,
            title,
            content,
            cleaned_payload,
            status,
            error_message,
            created_at
        FROM datasets
    """

    conditions: list[str] = []
    params: list[Any] = []

    if source is not None:
        conditions.append("source = %s")
        params.append(source)

    if status is not None:
        conditions.append("status = %s")
        params.append(status)

    if conditions:
        query = f"{query} WHERE {' AND '.join(conditions)}"

    query = f"{query} ORDER BY created_at DESC LIMIT %s"
    params.append(limit)

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
    except psycopg.Error as exc:
        logger.exception("Failed to read datasets")
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    return {"count": len(rows), "items": rows}


@app.get("/status")
def get_status() -> dict[str, Any]:
    status_report: dict[str, Any] = {
        "service": "api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall": "ok",
    }

    try:
        redis_client = get_redis_client()
        redis_ok = bool(redis_client.ping())
        status_report["redis"] = {
            "status": "ok" if redis_ok else "degraded",
            "scrape_queue_length": redis_client.llen(SCRAPE_QUEUE_NAME),
            "processing_queue_length": redis_client.llen(PROCESS_QUEUE_NAME),
        }
    except redis.RedisError as exc:
        status_report["redis"] = {"status": "down", "error": str(exc)}
        status_report["overall"] = "degraded"

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS dataset_count FROM datasets")
                dataset_count = cursor.fetchone()["dataset_count"]
        status_report["postgres"] = {"status": "ok", "dataset_count": dataset_count}
    except psycopg.Error as exc:
        status_report["postgres"] = {"status": "down", "error": str(exc)}
        status_report["overall"] = "degraded"

    return status_report