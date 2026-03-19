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


def _normalize_jsonb_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _fetch_latest_results(limit: int) -> list[dict[str, Any]]:
    query = """
        SELECT id, url, title, description, headings, links, created_at
        FROM scraped_data
        ORDER BY id DESC
        LIMIT %s;
    """

    with get_db_connection() as connection:
        print(
            f"DB connection success: db={connection.info.dbname}, host={connection.info.host}"
        )
        with connection.cursor() as cursor:
            cursor.execute(query, [limit])
            rows = cursor.fetchall()
            print(f"Rows fetched from scraped_data: {len(rows)}")

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized_rows.append(
            {
                "id": row["id"],
                "url": row["url"],
                "title": row["title"],
                "description": row["description"],
                "headings": _normalize_jsonb_list(row.get("headings")),
                "links": _normalize_jsonb_list(row.get("links")),
                "created_at": row["created_at"],
            }
        )

    return normalized_rows


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


@app.get("/results")
def get_results(limit: int = Query(default=10, ge=1, le=200)) -> dict[str, Any]:
    try:
        results = _fetch_latest_results(limit=limit)
    except psycopg.errors.UndefinedTable as exc:
        logger.exception("Table scraped_data does not exist")
        raise HTTPException(status_code=503, detail="Results table unavailable") from exc
    except psycopg.OperationalError as exc:
        logger.exception("Database connection error while fetching results")
        raise HTTPException(status_code=503, detail="Database connection failed") from exc
    except psycopg.Error as exc:
        logger.exception("Database error while fetching results")
        raise HTTPException(status_code=500, detail="Failed to fetch results") from exc

    return {"count": len(results), "data": results}


@app.get("/scraped_data")
def get_scraped_data(
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    query = """
        SELECT
            id,
            url,
            title,
            description,
            headings,
            links,
            created_at
        FROM scraped_data
        ORDER BY created_at DESC
        LIMIT %s
    """
    params: list[Any] = [limit]

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
    except psycopg.errors.UndefinedTable:
        logger.warning("Table scraped_data does not exist yet")
        return {"count": 0, "items": []}
    except psycopg.Error as exc:
        logger.exception("Failed to read scraped_data")
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
                cursor.execute("SELECT COUNT(*) AS scraped_data_count FROM scraped_data")
                scraped_data_count = cursor.fetchone()["scraped_data_count"]
        status_report["postgres"] = {"status": "ok", "scraped_data_count": scraped_data_count}
    except psycopg.errors.UndefinedTable:
        status_report["postgres"] = {
            "status": "degraded",
            "scraped_data_count": 0,
            "error": "table scraped_data does not exist",
        }
        status_report["overall"] = "degraded"
    except psycopg.Error as exc:
        status_report["postgres"] = {"status": "down", "error": str(exc)}
        status_report["overall"] = "degraded"

    return status_report