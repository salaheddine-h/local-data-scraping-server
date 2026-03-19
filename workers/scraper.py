from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.exceptions import RequestException


class ScrapeError(Exception):
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
    - links
    """
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ScraperBot/1.0"},
        )
        response.raise_for_status()
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
        "headings": headings,
        "links": unique_links,
    }