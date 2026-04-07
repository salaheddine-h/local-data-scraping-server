import json
import logging
import os
import time

from redis import Redis
from redis.exceptions import RedisError

from keyword_filter import filter_page_by_keywords
from scraper import ScrapeError, SSLVerificationError, scrape_page

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SCRAPE_QUEUE = os.getenv("SCRAPE_QUEUE_NAME", "scrape_queue")
PROCESS_QUEUE = os.getenv("PROCESS_QUEUE_NAME", "processing_tasks")
MAX_TASK_RETRIES = int(os.getenv("MAX_TASK_RETRIES", "2"))


def get_redis() -> Redis:
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    client.ping()
    return client


def _requeue_task(redis_client: Redis, task_data: dict, reason: str) -> bool:
    """Re-enqueue a failed task if it hasn't exceeded MAX_TASK_RETRIES."""
    retries = task_data.get("_retry_count", 0)
    if retries >= MAX_TASK_RETRIES:
        logger.error(
            "Task for %s exhausted %d retries (%s), dropping",
            task_data.get("url"),
            MAX_TASK_RETRIES,
            reason,
        )
        return False

    task_data["_retry_count"] = retries + 1
    redis_client.rpush(SCRAPE_QUEUE, json.dumps(task_data))
    logger.warning(
        "Re-queued %s (retry %d/%d): %s",
        task_data.get("url"),
        retries + 1,
        MAX_TASK_RETRIES,
        reason,
    )
    return True


def process_task(redis_client: Redis, payload: str):
    try:
        task_data = json.loads(payload)
    except json.JSONDecodeError:
        logger.error("Invalid JSON payload received: %s", payload)
        return

    url = task_data.get("url")
    keywords = task_data.get("keywords", [])
    metadata = task_data.get("metadata") if isinstance(task_data.get("metadata"), dict) else {}
    request_timeout = task_data.get("request_timeout", 15)
    if not isinstance(request_timeout, int) or request_timeout < 1:
        request_timeout = 15

    if not url:
        logger.warning("Missing URL in task payload: %s", payload)
        return

    # Validate keywords
    if not isinstance(keywords, list):
        keywords = []

    logger.info("Scraping URL: %s (keywords=%s)", url, keywords)
    start_time = time.monotonic()

    try:
        # Scrape data
        scraped_data = scrape_page(url, timeout=request_timeout)
    except SSLVerificationError as e:
        # SSL errors are not retryable — the cert won't fix itself
        logger.error("SSL verification failed for %s: %s", url, e)
        return
    except ScrapeError as e:
        logger.warning("Scrape failed for %s: %s", url, e)
        _requeue_task(redis_client, task_data, str(e))
        return
    except Exception as e:
        logger.exception("Unexpected error scraping %s: %s", url, e)
        _requeue_task(redis_client, task_data, str(e))
        return

    elapsed = time.monotonic() - start_time
    logger.info("Scraped %s in %.2fs", url, elapsed)

    # Send structured exact JSON schema to processor queue
    result_payload = {
        "url": scraped_data.get("url"),
        "title": scraped_data.get("title"),
        "description": scraped_data.get("description"),
        "content": scraped_data.get("content"),
        "headings": scraped_data.get("headings", []),
        "paragraphs": scraped_data.get("paragraphs", []),
        "links": scraped_data.get("links", []),
        "metadata": metadata,
    }

    # Keyword-based filtering
    if keywords:
        soup = scraped_data.get("soup")
        if soup:
            kw_result = filter_page_by_keywords(soup, keywords, url=url)
            result_payload["matched_keywords"] = kw_result.matched_keywords
            result_payload["extracted_snippets"] = kw_result.extracted_snippets
            logger.info(
                "Keyword filtering complete for %s: %d matched",
                url,
                len(kw_result.matched_keywords),
            )
        else:
            result_payload["matched_keywords"] = []
            result_payload["extracted_snippets"] = []

    redis_client.rpush(PROCESS_QUEUE, json.dumps(result_payload))
    logger.info("Successfully scraped and pushed to processing_tasks: %s", url)


def run_worker():
    redis_client = get_redis()
    logger.info("Worker started. Listening on Redis queue: %s", SCRAPE_QUEUE)

    while True:
        try:
            item = redis_client.blpop([SCRAPE_QUEUE], timeout=5)
            if not item:
                continue

            _, payload = item
            process_task(redis_client, payload)

        except RedisError as e:
            logger.error("Redis connection error: %s. Reconnecting in 5s...", e)
            time.sleep(5)
            redis_client = get_redis()
        except Exception as e:
            logger.exception("Error in worker loop: %s", e)
            time.sleep(2)


def main():
    while True:
        try:
            run_worker()
        except Exception as e:
            logger.error("Worker crashed: %s. Restarting in 5s...", e)
            time.sleep(5)


if __name__ == "__main__":
    main()