from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests import RequestException
from requests.exceptions import InvalidURL, SSLError


class ScrapeError(Exception):
    pass


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def scrape_page(url: str, timeout: int = 20) -> dict[str, object]:
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "LocalDataScrapingWorker/1.0"},
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        raise ScrapeError(f"Request timed out for URL: {url}") from exc
    except InvalidURL as exc:
        raise ScrapeError(f"Invalid URL: {url}") from exc
    except SSLError as exc:
        raise ScrapeError(f"SSL error while fetching {url}: {exc}") from exc
    except RequestException as exc:
        raise ScrapeError(f"Network error while fetching {url}: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")

    title = _normalize_text(soup.title.string if soup.title else None)
    description_tag = soup.find("meta", attrs={"name": "description"})
    description = _normalize_text(description_tag.get("content") if description_tag else None)

    headings: list[str] = []
    for tag_name in ("h1", "h2", "h3"):
        for node in soup.find_all(tag_name):
            text = _normalize_text(node.get_text(separator=" "))
            if text:
                headings.append(text)

    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if not href:
            continue
        absolute_link = urljoin(url, href)
        if absolute_link.startswith("http://") or absolute_link.startswith("https://"):
            links.append(absolute_link)

    unique_links = list(dict.fromkeys(links))

    return {
        "url": url,
        "title": title,
        "description": description,
        "headings": headings,
        "links": unique_links,
    }