import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp
from redis import asyncio as redis


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


configure_logging()
logger = logging.getLogger("scraper-worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SCRAPE_QUEUE_NAME = os.getenv("SCRAPE_QUEUE_NAME", "scrape_tasks")
PROCESS_QUEUE_NAME = os.getenv("PROCESS_QUEUE_NAME", "processing_tasks")
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "5"))


async def fetch_payload(
    session: aiohttp.ClientSession,
    url: str,
    request_timeout: int,
) -> tuple[Any, str, int]:
    timeout = aiohttp.ClientTimeout(total=request_timeout)

    async with session.get(url, timeout=timeout) as response:
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "application/octet-stream")

        if "application/json" in content_type:
            data = await response.json(content_type=None)
        else:
            data = await response.text()

        return data, content_type, response.status


async def publish_result(redis_client: redis.Redis, message: dict[str, Any]) -> None:
    await redis_client.rpush(PROCESS_QUEUE_NAME, json.dumps(message, default=str))


async def handle_job(
    redis_client: redis.Redis,
    session: aiohttp.ClientSession,
    payload: str,
) -> None:
    task_data = json.loads(payload)
    task_id = task_data["task_id"]
    url = task_data["url"]
    source = task_data.get("source", "manual")
    request_timeout = int(task_data.get("request_timeout", 20))

    logger.info("Fetching task %s from %s", task_id, url)

    try:
        raw_data, content_type, status_code = await fetch_payload(session, url, request_timeout)
        result = {
            "task_id": task_id,
            "url": url,
            "source": source,
            "status": "success",
            "http_status": status_code,
            "content_type": content_type,
            "raw_data": raw_data,
            "metadata": task_data.get("metadata", {}),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
        await publish_result(redis_client, result)
        logger.info("Task %s fetched successfully", task_id)
    except Exception as exc:
        logger.exception("Task %s failed", task_id)
        result = {
            "task_id": task_id,
            "url": url,
            "source": source,
            "status": "failed",
            "error": str(exc),
            "metadata": task_data.get("metadata", {}),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
        await publish_result(redis_client, result)


def log_task_result(task: asyncio.Task[None]) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        logger.warning("Worker task cancelled")
    except Exception:
        logger.exception("Unhandled worker task failure")


async def run_worker() -> None:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    connector = aiohttp.TCPConnector(limit_per_host=max(WORKER_CONCURRENCY * 2, 10))
    headers = {"User-Agent": "LocalDataPlatformWorker/0.1"}

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        active_tasks: set[asyncio.Task[None]] = set()

        while True:
            active_tasks = {task for task in active_tasks if not task.done()}

            if len(active_tasks) >= WORKER_CONCURRENCY:
                await asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)
                continue

            queue_item = await redis_client.blpop(SCRAPE_QUEUE_NAME, timeout=5)
            if queue_item is None:
                continue

            _, payload = queue_item
            job = asyncio.create_task(handle_job(redis_client, session, payload))
            job.add_done_callback(log_task_result)
            active_tasks.add(job)


async def main() -> None:
    while True:
        try:
            await run_worker()
        except Exception:
            logger.exception("Worker loop crashed, retrying in 5 seconds")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())