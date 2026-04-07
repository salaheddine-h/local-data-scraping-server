"""Unit tests for the keyword_filter module."""

import pytest
from bs4 import BeautifulSoup

from workers.keyword_filter import (
    KeywordResult,
    TextBlock,
    extract_snippets,
    extract_text_blocks,
    filter_page_by_keywords,
    find_keyword_matches,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


SAMPLE_HTML = """
<html>
<head><title>Learn Python and Backend Development</title></head>
<body>
  <h1>Python Programming Guide</h1>
  <h2>Getting Started with AI</h2>
  <p>Python is a versatile language used in backend development and AI research.</p>
  <p>This guide covers best practices for building scalable backend systems.</p>
  <p>Machine learning frameworks like TensorFlow use Python extensively.</p>
  <h3>Advanced Topics</h3>
  <p>Explore deep learning, natural language processing, and more.</p>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# extract_text_blocks
# ---------------------------------------------------------------------------

class TestExtractTextBlocks:
    def test_extracts_title(self):
        blocks = extract_text_blocks(_soup("<html><head><title>Hello</title></head></html>"))
        assert any(b.tag == "title" and b.text == "Hello" for b in blocks)

    def test_extracts_headings(self):
        blocks = extract_text_blocks(_soup("<h1>First</h1><h2>Second</h2>"))
        tags = [b.tag for b in blocks]
        assert "h1" in tags
        assert "h2" in tags

    def test_extracts_paragraphs(self):
        blocks = extract_text_blocks(_soup("<p>Para one</p><p>Para two</p>"))
        texts = [b.text for b in blocks if b.tag == "p"]
        assert texts == ["Para one", "Para two"]

    def test_skips_empty_text(self):
        blocks = extract_text_blocks(_soup("<p>   </p><p>Real text</p>"))
        texts = [b.text for b in blocks if b.tag == "p"]
        assert texts == ["Real text"]

    def test_empty_html(self):
        blocks = extract_text_blocks(_soup(""))
        assert blocks == []

    def test_sample_html_block_count(self):
        blocks = extract_text_blocks(_soup(SAMPLE_HTML))
        # 1 title + 3 headings + 4 paragraphs = 8
        assert len(blocks) == 8


# ---------------------------------------------------------------------------
# find_keyword_matches
# ---------------------------------------------------------------------------

class TestFindKeywordMatches:
    def test_basic_match(self):
        blocks = [TextBlock("p", "Python is great"), TextBlock("p", "Learn AI today")]
        matched = find_keyword_matches(blocks, ["python", "AI"])
        assert set(matched) == {"python", "AI"}

    def test_case_insensitive(self):
        blocks = [TextBlock("p", "PYTHON is here")]
        matched = find_keyword_matches(blocks, ["python"])
        assert matched == ["python"]

    def test_no_match(self):
        blocks = [TextBlock("p", "Hello world")]
        matched = find_keyword_matches(blocks, ["python"])
        assert matched == []

    def test_empty_keywords(self):
        blocks = [TextBlock("p", "Hello")]
        assert find_keyword_matches(blocks, []) == []

    def test_empty_blocks(self):
        assert find_keyword_matches([], ["python"]) == []

    def test_deduplicates_keywords(self):
        blocks = [TextBlock("p", "Python rocks")]
        matched = find_keyword_matches(blocks, ["python", "Python", "PYTHON"])
        assert matched == ["python"]

    def test_whitespace_keywords_ignored(self):
        blocks = [TextBlock("p", "Hello")]
        matched = find_keyword_matches(blocks, ["", "  ", "Hello"])
        assert matched == ["Hello"]


# ---------------------------------------------------------------------------
# extract_snippets
# ---------------------------------------------------------------------------

class TestExtractSnippets:
    def test_single_occurrence(self):
        text = "The quick brown fox jumps over the lazy dog"
        snippets = extract_snippets(text, "fox", context_chars=10)
        assert len(snippets) == 1
        assert "fox" in snippets[0]

    def test_multiple_occurrences(self):
        text = "Python is great. I love Python. Python forever."
        snippets = extract_snippets(text, "Python", context_chars=5)
        assert len(snippets) == 3

    def test_case_insensitive(self):
        text = "Learn PYTHON today"
        snippets = extract_snippets(text, "python", context_chars=50)
        assert len(snippets) == 1
        assert "PYTHON" in snippets[0]

    def test_ellipsis_when_truncated(self):
        text = "A" * 200 + " keyword " + "B" * 200
        snippets = extract_snippets(text, "keyword", context_chars=20)
        assert len(snippets) == 1
        assert snippets[0].startswith("…")
        assert snippets[0].endswith("…")

    def test_no_ellipsis_at_boundaries(self):
        text = "keyword at start"
        snippets = extract_snippets(text, "keyword", context_chars=100)
        assert len(snippets) == 1
        assert not snippets[0].startswith("…")

    def test_empty_text(self):
        assert extract_snippets("", "keyword") == []

    def test_empty_keyword(self):
        assert extract_snippets("some text", "") == []


# ---------------------------------------------------------------------------
# filter_page_by_keywords (integration)
# ---------------------------------------------------------------------------

class TestFilterPageByKeywords:
    def test_full_pipeline(self):
        result = filter_page_by_keywords(
            _soup(SAMPLE_HTML),
            ["python", "backend", "AI"],
            url="https://example.com",
        )

        assert isinstance(result, KeywordResult)
        assert result.url == "https://example.com"
        assert result.title == "Learn Python and Backend Development"
        assert set(result.matched_keywords) == {"python", "backend", "AI"}
        assert len(result.extracted_snippets) > 0

        # Each snippet has required keys
        for s in result.extracted_snippets:
            assert "keyword" in s
            assert "snippet" in s

    def test_no_matches(self):
        result = filter_page_by_keywords(
            _soup(SAMPLE_HTML),
            ["golang", "rust"],
            url="https://example.com",
        )
        assert result.matched_keywords == []
        assert result.extracted_snippets == []

    def test_empty_keywords(self):
        result = filter_page_by_keywords(_soup(SAMPLE_HTML), [])
        assert result.matched_keywords == []
        assert result.extracted_snippets == []

    def test_empty_html(self):
        result = filter_page_by_keywords(_soup(""), ["python"])
        assert result.matched_keywords == []

    def test_result_snippet_keyword_field_matches(self):
        result = filter_page_by_keywords(
            _soup(SAMPLE_HTML),
            ["python"],
            url="https://example.com",
        )
        for s in result.extracted_snippets:
            assert s["keyword"] == "python"
