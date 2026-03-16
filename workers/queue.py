import json
from typing import Any

from redis import Redis


def connect_redis(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, decode_responses=True)


def pop_scrape_task(
    redis_client: Redis,
    queue_names: list[str],
    timeout_seconds: int,
) -> tuple[str, str] | None:
    if not queue_names:
        return None
    return redis_client.blpop(queue_names, timeout=timeout_seconds)


def push_processing_result(
    redis_client: Redis,
    queue_name: str,
    message: dict[str, Any],
) -> None:
    redis_client.rpush(queue_name, json.dumps(message, default=str))