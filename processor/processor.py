import html
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import psycopg
import redis
from psycopg.types.json import Jsonb


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


configure_logging()
logger = logging.getLogger("processor")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app@postgres:5432/local_data")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
PROCESS_QUEUE_NAME = os.getenv("PROCESS_QUEUE_NAME", "processing_tasks")


def get_redis_client() -> redis.Redis:
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


def get_db_connection() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, autocommit=True)


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_html(value: str) -> str:
    return collapse_whitespace(re.sub(r"<[^>]+>", " ", html.unescape(value)))


def pick_text_field(data: dict[str, Any], candidates: list[str]) -> str | None:
    for key in candidates:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return collapse_whitespace(value)
    return None


def normalize_item(item: Any, source: str, url: str, task_id: str) -> dict[str, Any]:
    if isinstance(item, dict):
        title = pick_text_field(item, ["title", "name", "headline"])
        content = pick_text_field(item, ["body", "description", "content", "text", "summary"])
        return {
            "task_id": task_id,
            "source": source,
            "url": url,
            "title": title,
            "content": content,
            "raw_payload": item,
            "cleaned_payload": item,
            "status": "processed",
            "error_message": None,
        }

    if isinstance(item, str):
        cleaned_text = strip_html(item)
        title = cleaned_text[:80] if cleaned_text else None
        return {
            "task_id": task_id,
            "source": source,
            "url": url,
            "title": title,
            "content": cleaned_text or None,
            "raw_payload": {"text": item},
            "cleaned_payload": {"text": cleaned_text},
            "status": "processed",
            "error_message": None,
        }

    serialized = collapse_whitespace(json.dumps(item, default=str))
    return {
        "task_id": task_id,
        "source": source,
        "url": url,
        "title": serialized[:80] if serialized else None,
        "content": serialized or None,
        "raw_payload": {"value": item},
        "cleaned_payload": {"value": item},
        "status": "processed",
        "error_message": None,
    }


def normalize_message(message: dict[str, Any]) -> list[dict[str, Any]]:
    task_id = message["task_id"]
    source = message.get("source", "manual")
    url = message["url"]

    if message.get("status") != "success":
        return [
            {
                "task_id": task_id,
                "source": source,
                "url": url,
                "title": None,
                "content": None,
                "raw_payload": message,
                "cleaned_payload": None,
                "status": "failed",
                "error_message": message.get("error", "Unknown scraping error"),
            }
        ]

    raw_data = message.get("raw_data")
    if isinstance(raw_data, list):
        items = raw_data
    else:
        items = [raw_data]

    return [normalize_item(item, source, url, task_id) for item in items]


def persist_records(connection: psycopg.Connection, records: list[dict[str, Any]]) -> None:
    insert_sql = """
        INSERT INTO datasets (
            task_id,
            source,
            url,
            title,
            content,
            raw_payload,
            cleaned_payload,
            status,
            error_message,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    with connection.cursor() as cursor:
        for record in records:
            cursor.execute(
                insert_sql,
                (
                    record["task_id"],
                    record["source"],
                    record["url"],
                    record["title"],
                    record["content"],
                    Jsonb(record["raw_payload"]) if record["raw_payload"] is not None else None,
                    Jsonb(record["cleaned_payload"]) if record["cleaned_payload"] is not None else None,
                    record["status"],
                    record["error_message"],
                    datetime.now(timezone.utc),
                ),
            )


def run_processor() -> None:
    redis_client = get_redis_client()
    db_connection = get_db_connection()

    logger.info("Processor started")

    while True:
        queue_item = redis_client.blpop(PROCESS_QUEUE_NAME, timeout=5)
        if queue_item is None:
            continue

        _, payload = queue_item
        message = json.loads(payload)
        records = normalize_message(message)
        persist_records(db_connection, records)
        logger.info("Stored %s dataset record(s) for task %s", len(records), message["task_id"])


def main() -> None:
    while True:
        try:
            run_processor()
        except Exception:
            logger.exception("Processor loop crashed, retrying in 5 seconds")
            time.sleep(5)


if __name__ == "__main__":
    main()