import json
import logging
import os
import time

from redis import Redis
from redis.exceptions import RedisError

from scraper import ScrapeError, scrape_page

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SCRAPE_QUEUE = "scrape_queue"
PROCESS_QUEUE = "processing_tasks"


def get_redis() -> Redis:
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    client.ping()
    return client


def process_task(redis_client: Redis, payload: str):
    try:
        task_data = json.loads(payload)
        url = task_data.get("url")

        if not url:
            logger.warning("Missing URL in task payload: %s", payload)
            return

        logger.info("Scraping URL: %s", url)

        # Scrape data
        scraped_data = scrape_page(url)

        # Send structured exact JSON schema to processor queue
        result_payload = {
            "url": scraped_data.get("url"),
            "title": scraped_data.get("title"),
            "description": scraped_data.get("description"),
            "headings": scraped_data.get("headings", []),
            "links": scraped_data.get("links", []),
        }

        redis_client.rpush(PROCESS_QUEUE, json.dumps(result_payload))
        logger.info("Successfully scraped and pushed to processing_tasks: %s", url)

    except json.JSONDecodeError:
        logger.error("Invalid JSON payload received: %s", payload)
    except ScrapeError as e:
        logger.error("Failed to scrape URL: %s", e)
    except Exception as e:
        logger.exception("Unexpected error processing task: %s", e)


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