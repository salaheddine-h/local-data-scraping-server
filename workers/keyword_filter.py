"""
Keyword-based filtering for scraped HTML content.

Provides utilities to extract structured text blocks from a BeautifulSoup
document, search for keywords, and return contextual snippets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from bs4 import BeautifulSoup, Tag


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TextBlock:
    """A labelled chunk of text extracted from an HTML page."""

    tag: str          # e.g. "title", "h1", "p"
    text: str         # cleaned text content


@dataclass
class KeywordResult:
    """Aggregated result of keyword filtering on a single page."""

    url: str
    title: str | None
    matched_keywords: list[str] = field(default_factory=list)
    extracted_snippets: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

_TEXT_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th",
              "blockquote", "figcaption", "caption")


def _clean(text: str | None) -> str:
    """Collapse whitespace and strip a string."""
    if not text:
        return ""
    return " ".join(text.split()).strip()


def extract_text_blocks(soup: BeautifulSoup) -> list[TextBlock]:
    """
    Pull structured text blocks out of a parsed HTML document.

    Returns blocks for the ``<title>`` and common content tags such as
    headings, paragraphs, and list items.
    """
    blocks: list[TextBlock] = []

    # Title
    if soup.title and soup.title.string:
        cleaned = _clean(soup.title.string)
        if cleaned:
            blocks.append(TextBlock(tag="title", text=cleaned))

    # Body content tags
    for tag_name in _TEXT_TAGS:
        for node in soup.find_all(tag_name):
            if not isinstance(node, Tag):
                continue
            cleaned = _clean(node.get_text())
            if cleaned:
                blocks.append(TextBlock(tag=tag_name, text=cleaned))

    return blocks


# ---------------------------------------------------------------------------
# Keyword matching
# ---------------------------------------------------------------------------

def find_keyword_matches(
    text_blocks: Sequence[TextBlock],
    keywords: Sequence[str],
) -> list[str]:
    """
    Return the *subset* of *keywords* that appear (case-insensitively) in any
    of the given *text_blocks*.

    Duplicates in *keywords* are ignored; order is preserved.
    """
    if not keywords:
        return []

    # Build a single corpus for fast scanning
    corpus = " ".join(block.text for block in text_blocks).casefold()

    seen: set[str] = set()
    matched: list[str] = []

    for kw in keywords:
        normalised = kw.strip()
        if not normalised:
            continue
        key = normalised.casefold()
        if key in seen:
            continue
        seen.add(key)
        if key in corpus:
            matched.append(normalised)

    return matched


# ---------------------------------------------------------------------------
# Snippet extraction
# ---------------------------------------------------------------------------

def extract_snippets(
    text: str,
    keyword: str,
    context_chars: int = 100,
) -> list[str]:
    """
    Find every occurrence of *keyword* (case-insensitive) in *text* and return
    a list of snippets, each containing up to *context_chars* characters of
    surrounding context on either side.
    """
    if not text or not keyword:
        return []

    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    snippets: list[str] = []

    for match in pattern.finditer(text):
        start = max(0, match.start() - context_chars)
        end = min(len(text), match.end() + context_chars)

        snippet = text[start:end].strip()

        # Add ellipsis when we've truncated
        if start > 0:
            snippet = f"…{snippet}"
        if end < len(text):
            snippet = f"{snippet}…"

        snippets.append(snippet)

    return snippets


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------

def filter_page_by_keywords(
    soup: BeautifulSoup,
    keywords: Sequence[str],
    *,
    url: str = "",
    context_chars: int = 100,
) -> KeywordResult:
    """
    End-to-end keyword filtering on a parsed HTML page.

    1. Extract text blocks (title, headings, paragraphs, etc.)
    2. Determine which keywords match
    3. Pull contextual snippets for every matched keyword

    Returns a :class:`KeywordResult` with ``matched_keywords`` and
    ``extracted_snippets``.
    """
    blocks = extract_text_blocks(soup)

    # Title for the result
    title_block = next((b for b in blocks if b.tag == "title"), None)
    title = title_block.text if title_block else None

    matched = find_keyword_matches(blocks, keywords)

    # Collect snippets per matched keyword
    full_text = " ".join(block.text for block in blocks)
    all_snippets: list[dict[str, str]] = []

    for kw in matched:
        for snippet in extract_snippets(full_text, kw, context_chars=context_chars):
            all_snippets.append({"keyword": kw, "snippet": snippet})

    return KeywordResult(
        url=url,
        title=title,
        matched_keywords=matched,
        extracted_snippets=all_snippets,
    )
