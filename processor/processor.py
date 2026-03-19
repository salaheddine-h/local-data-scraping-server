import json
import logging
import os
import time

import psycopg
import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("processor")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app@postgres:5432/local_data")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
PROCESS_QUEUE = "processing_tasks"


def get_redis() -> redis.Redis:
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


def get_db() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)


def process_tasks():
    redis_client = get_redis()
    db_conn = get_db()

    logger.info("Processor listening on queue: %s", PROCESS_QUEUE)

    while True:
        try:
            item = redis_client.blpop(PROCESS_QUEUE, timeout=5)
            if not item:
                continue

            _, payload = item
            data = json.loads(payload)

            url = data.get("url")
            title = data.get("title")
            description = data.get("description")
            headings = data.get("headings", [])
            links = data.get("links", [])

            if not url:
                logger.warning("Received payload without URL, skipping: %s", data)
                continue

            # Clean/Validate strings
            title = title.strip() if isinstance(title, str) else None
            description = description.strip() if isinstance(description, str) else None

            # Clean/Validate lists
            headings = [str(h).strip() for h in headings if str(h).strip()] if isinstance(headings, list) else []
            links = [str(link).strip() for link in links if str(link).strip()] if isinstance(links, list) else []
            headings_json = json.dumps(headings)
            links_json = json.dumps(links)

            insert_sql = """
                INSERT INTO public.scraped_data (url, title, description, headings, links)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
            """

            logger.info("Attempting insert into public.scraped_data for URL: %s", url)

            try:
                with db_conn.cursor() as cursor:
                    cursor.execute(
                        insert_sql,
                        (url, title, description, headings_json, links_json),
                    )
                db_conn.commit()
                logger.info("Insert committed to public.scraped_data for URL: %s", url)
            except psycopg.Error as e:
                db_conn.rollback()
                logger.exception("Insert failed and rolled back for URL %s: %s", url, e)
                continue

            logger.info("Successfully stored data for URL: %s", url)

        except json.JSONDecodeError:
            logger.error("Failed to decode JSON payload: %s", payload)
        except psycopg.Error as e:
            logger.error("Database error inserting data into scraped_data: %s", e)
        except Exception as e:
            logger.exception("Error processing task: %s", e)
            time.sleep(2)


def main():
    while True:
        try:
            process_tasks()
        except Exception as e:
            logger.error("Processor loop crashed: %s. Retrying in 5 seconds...", e)
            time.sleep(5)


if __name__ == "__main__":
    main()