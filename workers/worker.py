import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from redis import Redis
from redis.exceptions import RedisError

from workers.queue import (
    connect_redis,
    pop_scrape_task,
    push_processing_result,
)
from workers.scraper import ScrapeError, scrape_page


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


configure_logging()
logger = logging.getLogger("scraper-worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SCRAPE_QUEUE_NAME = os.getenv("SCRAPE_QUEUE_NAME", "scrape_queue")
LEGACY_SCRAPE_QUEUE_NAME = os.getenv("LEGACY_SCRAPE_QUEUE_NAME", "scrape_tasks")
PROCESS_QUEUE_NAME = os.getenv("PROCESS_QUEUE_NAME", "processing_tasks")
DEFAULT_REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
POLL_TIMEOUT_SECONDS = int(os.getenv("QUEUE_POLL_TIMEOUT", "5"))
RETRY_DELAY_SECONDS = int(os.getenv("WORKER_RETRY_DELAY", "5"))


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_task(payload: str) -> dict[str, Any]:
    task_data = json.loads(payload)
    task_data.setdefault("task_id", str(uuid.uuid4()))
    task_data.setdefault("source", "manual")
    task_data.setdefault("metadata", {})
    task_data.setdefault("request_timeout", DEFAULT_REQUEST_TIMEOUT)
    return task_data


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def build_success_result(task_data: dict[str, Any], scraped_data: dict[str, Any]) -> dict[str, Any]:
    task_id = task_data["task_id"]
    url = task_data["url"]
    source = task_data.get("source", "manual")
    return {
        "task_id": task_id,
        "url": url,
        "source": source,
        "status": "success",
        "raw_data": scraped_data,
        "metadata": task_data.get("metadata", {}),
        "scraped_at": now_utc_iso(),
    }


def build_failure_result(task_data: dict[str, Any], error_message: str) -> dict[str, Any]:
    return {
        "task_id": task_data["task_id"],
        "url": task_data.get("url", ""),
        "source": task_data.get("source", "manual"),
        "status": "failed",
        "error": error_message,
        "metadata": task_data.get("metadata", {}),
        "scraped_at": now_utc_iso(),
    }


def process_single_task(redis_client: Redis, payload: str) -> None:
    task_data = normalize_task(payload)
    url = task_data.get("url", "")

    if not isinstance(url, str) or not is_valid_url(url):
        logger.warning("Task %s rejected due to invalid URL: %s", task_data["task_id"], url)
        result = build_failure_result(task_data, f"Invalid URL: {url}")
        push_processing_result(redis_client, PROCESS_QUEUE_NAME, result)
        return

    request_timeout = int(task_data.get("request_timeout", DEFAULT_REQUEST_TIMEOUT))
    logger.info("Scraping task %s from %s", task_data["task_id"], url)

    try:
        scraped_data = scrape_page(url, timeout=request_timeout)
        result = build_success_result(task_data, scraped_data)
        push_processing_result(redis_client, PROCESS_QUEUE_NAME, result)
        logger.info("Task %s processed successfully", task_data["task_id"])
    except ScrapeError as exc:
        logger.warning("Task %s failed: %s", task_data["task_id"], exc)
        result = build_failure_result(task_data, str(exc))
        push_processing_result(redis_client, PROCESS_QUEUE_NAME, result)
    except Exception as exc:
        logger.exception("Task %s crashed", task_data["task_id"])
        result = build_failure_result(task_data, f"Unhandled worker error: {exc}")
        push_processing_result(redis_client, PROCESS_QUEUE_NAME, result)


def run_worker() -> None:
    redis_client = connect_redis(REDIS_URL)
    queue_names = [SCRAPE_QUEUE_NAME]
    if LEGACY_SCRAPE_QUEUE_NAME and LEGACY_SCRAPE_QUEUE_NAME != SCRAPE_QUEUE_NAME:
        queue_names.append(LEGACY_SCRAPE_QUEUE_NAME)

    logger.info("Worker started. Listening on queues: %s", ", ".join(queue_names))

    while True:
        queue_item = pop_scrape_task(redis_client, queue_names, POLL_TIMEOUT_SECONDS)
        if queue_item is None:
            continue

        _, payload = queue_item
        process_single_task(redis_client, payload)


def main() -> None:
    while True:
        try:
            run_worker()
        except RedisError:
            logger.exception("Worker loop crashed, retrying in 5 seconds")
            time.sleep(RETRY_DELAY_SECONDS)
        except Exception:
            logger.exception("Unexpected fatal worker error, retrying in 5 seconds")
            time.sleep(RETRY_DELAY_SECONDS)


if __name__ == "__main__":
    main()