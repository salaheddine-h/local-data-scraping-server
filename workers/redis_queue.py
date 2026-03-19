import json
import logging
from typing import Any

from redis import Redis

logger = logging.getLogger("scraper-worker")


def connect_redis(redis_url: str) -> Redis:
    redis_client = Redis.from_url(redis_url, decode_responses=True)
    redis_client.ping()
    logger.info("Connected to Redis at %s", redis_url)
    return redis_client


def pop_scrape_task(
    redis_client: Redis,
    queue_names: list[str],
    timeout_seconds: int,
) -> tuple[str, str] | None:
    if not queue_names:
        return None
    result = redis_client.blpop(queue_names, timeout=timeout_seconds)
    if result is not None:
        queue_name, payload = result
        logger.debug("Popped task from queue '%s'", queue_name)
    return result


def push_processing_result(
    redis_client: Redis,
    queue_name: str,
    message: dict[str, Any],
) -> None:
    redis_client.rpush(queue_name, json.dumps(message, default=str))
    logger.debug("Pushed result to queue '%s' for task %s", queue_name, message.get("task_id"))