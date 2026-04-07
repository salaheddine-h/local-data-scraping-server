import logging
from urllib.parse import urljoin

import certifi
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException, SSLError
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Resolve CA bundle path once at import time
CA_BUNDLE = certifi.where()
logger.debug("Using CA bundle: %s", CA_BUNDLE)

# Retry strategy: 3 retries with exponential backoff on transient errors
_RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=1,                          # 1s, 2s, 4s
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "HEAD"],
    raise_on_status=False,
)


def _build_session() -> requests.Session:
    """Create a requests Session with retry adapter and SSL configuration."""
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=_RETRY_STRATEGY)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.verify = CA_BUNDLE
    session.headers.update(
        {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ScraperBot/1.0"}
    )
    return session


# Module-level session — reused across calls for connection pooling
_session = _build_session()


class ScrapeError(Exception):
    pass


class SSLVerificationError(ScrapeError):
    """Raised specifically for SSL certificate issues."""

    pass


def _clean_text(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = " ".join(text.split()).strip()
    return cleaned if cleaned else None


def scrape_page(url: str, timeout: int = 15) -> dict:
    """
    Fetches the URL and extracts:
    - title
    - meta description
    - headings (h1, h2, h3)
    - paragraphs
    - links

    Uses a persistent session with automatic retries on transient failures.
    SSL verification uses the certifi CA bundle explicitly.
    """
    try:
        response = _session.get(url, timeout=timeout)
        response.raise_for_status()
    except SSLError as e:
        raise SSLVerificationError(
            f"SSL certificate verification failed for {url}: {e}"
        ) from e
    except RequestException as e:
        raise ScrapeError(f"Network error fetching {url}: {e}") from e

    soup = BeautifulSoup(response.text, "html.parser")

    # Title
    title = _clean_text(soup.title.string if soup.title else None)

    # Meta Description
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    description = _clean_text(meta_desc_tag.get("content") if meta_desc_tag else None)

    # Headings
    headings = []
    for tag in ("h1", "h2", "h3"):
        for node in soup.find_all(tag):
            text = _clean_text(node.get_text())
            if text:
                headings.append(text)

    # Paragraphs
    paragraphs = []
    for node in soup.find_all("p"):
        text = _clean_text(node.get_text())
        if text:
            paragraphs.append(text)

    # Links
    links = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href")
        if href:
            absolute_link = urljoin(url, href)
            if absolute_link.startswith(("http://", "https://")):
                links.append(absolute_link)

    # Dedup links while preserving order
    unique_links = list(dict.fromkeys(links))

    return {
        "url": url,
        "title": title,
        "description": description,
        "content": response.text,
        "headings": headings,
        "paragraphs": paragraphs,
        "links": unique_links,
        "soup": soup,
    }