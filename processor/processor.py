import json
import logging
import os
import time
from typing import Any

import psycopg
import redis
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("processor")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app@postgres:5432/local_data")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
PROCESS_QUEUE = "processing_tasks"


def get_redis() -> redis.Redis:
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


def get_db() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)


def extract_plain_text(content: Any) -> str:
    if not isinstance(content, str):
        return ""

    stripped = content.strip()
    if not stripped:
        return ""

    if "<" in stripped and ">" in stripped:
        text = BeautifulSoup(stripped, "html.parser").get_text(" ", strip=True)
    else:
        text = stripped

    return " ".join(text.split())


def extract_keyword_matches(content: str, keywords: Any) -> list[str]:
    if not content or not isinstance(keywords, list):
        return []

    content_casefold = content.casefold()
    seen_keywords: set[str] = set()
    matches: list[str] = []

    for keyword in keywords:
        if not isinstance(keyword, str):
            continue

        normalized = keyword.strip()
        if not normalized:
            continue

        normalized_casefold = normalized.casefold()
        if normalized_casefold in seen_keywords:
            continue

        seen_keywords.add(normalized_casefold)
        if normalized_casefold in content_casefold:
            matches.append(normalized)

    return matches


def _passes_optional_filters(content: str, metadata: dict[str, Any]) -> bool:
    min_length = metadata.get("min_length")
    if isinstance(min_length, int) and min_length > 0 and len(content) < min_length:
        return False
    return True


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
            raw_content = data.get("content")
            headings = data.get("headings", [])
            links = data.get("links", [])
            metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}

            if not url:
                logger.warning("Received payload without URL, skipping: %s", data)
                continue

            # Clean/Validate strings
            title = title.strip() if isinstance(title, str) else None
            description = description.strip() if isinstance(description, str) else None
            content = extract_plain_text(raw_content)

            if not content:
                fallback_parts = []
                if title:
                    fallback_parts.append(title)
                if description:
                    fallback_parts.append(description)
                if isinstance(headings, list):
                    fallback_parts.extend(str(h).strip() for h in headings if str(h).strip())
                content = " ".join(fallback_parts).strip()

            keyword_matches = extract_keyword_matches(content, metadata.get("keywords"))

            if not _passes_optional_filters(content, metadata):
                logger.info("Skipping URL due to optional filters: %s", url)
                continue

            # Clean/Validate lists
            headings = [str(h).strip() for h in headings if str(h).strip()] if isinstance(headings, list) else []
            links = [str(link).strip() for link in links if str(link).strip()] if isinstance(links, list) else []
            headings_json = json.dumps(headings)
            links_json = json.dumps(links)
            matches_json = json.dumps(keyword_matches)
            metadata_json = json.dumps(metadata)

            processed_result = {
                "url": url,
                "title": title,
                "content": content,
                "matches": keyword_matches,
            }
            logger.info("Processed result for %s: %s", url, processed_result)

            insert_sql = """
                INSERT INTO public.scraped_data (url, title, description, content, headings, links, matches, metadata)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
            """

            logger.info("Attempting insert into public.scraped_data for URL: %s", url)

            try:
                with db_conn.cursor() as cursor:
                    cursor.execute(
                        insert_sql,
                        (url, title, description, content, headings_json, links_json, matches_json, metadata_json),
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