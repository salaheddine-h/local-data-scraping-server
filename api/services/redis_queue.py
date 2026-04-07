import json
import logging
import os
import uuid
from datetime import datetime, timezone

import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SCRAPE_QUEUE_NAME = os.getenv("SCRAPE_QUEUE_NAME", "scrape_queue")
PROCESS_QUEUE_NAME = os.getenv("PROCESS_QUEUE_NAME", "processing_tasks")


def get_redis_client() -> redis.Redis:
    """Returns a connected Redis client, raising an exception if unavailable."""
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    client.ping()
    return client


def enqueue_task(url: str, source: str, keywords: list[str], metadata: dict, request_timeout: int) -> dict:
    """
    Constructs a task payload and enqueues it to Redis.
    Logs and raises errors if Redis is unavailable.
    """
    task_id = str(uuid.uuid4())
    task_payload = {
        "task_id": task_id,
        "url": url,
        "source": source,
        "keywords": keywords,
        "metadata": metadata,
        "request_timeout": request_timeout,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        redis_client = get_redis_client()
        redis_client.rpush(SCRAPE_QUEUE_NAME, json.dumps(task_payload))
        logger.info("Enqueued task %s for URL %s", task_id, url)
    except redis.RedisError as exc:
        logger.error("Failed to enqueue task %s: %s", task_id, exc)
        raise

    return {
        "status": "queued",
        "queue": SCRAPE_QUEUE_NAME,
        "task_id": task_id,
    }


def check_redis_health() -> dict:
    """
    Returns the Redis queue lengths and connection status safely.
    """
    try:
        client = get_redis_client()
        return {
            "status": "ok",
            "scrape_queue_length": client.llen(SCRAPE_QUEUE_NAME),
            "processing_queue_length": client.llen(PROCESS_QUEUE_NAME),
        }
    except redis.RedisError as exc:
        logger.warning("Redis health check failed: %s", exc)
        return {"status": "down", "error": str(exc)}
