"""
Unit tests for the WebSearcher component.

Covers web search (Brave API + DuckDuckGo fallback via ddgs), raw content
retrieval, the SSRF-protection URL safety check, and ingestion of web
content into the database.
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
import requests
from ddgs.exceptions import DDGSException

from src.components.retrieval.web_searcher import (
    WebContent,
    WebSearcher,
    WebSearchResult,
    _clean_web_text,
)

# ==================== INITIALIZATION TESTS ====================


def test_web_searcher_initialization(
    mock_document_processor, mock_document_repository
):
    """Test successful WebSearcher initialization with a configured API key."""
    with patch("src.components.retrieval.web_searcher.settings") as mock_settings:
        mock_settings.web.BRAVE_SEARCH_API_KEY.get_secret_value.return_value = (
            "test_api_key"
        )

        searcher = WebSearcher(
            document_processor=mock_document_processor,
            document_repository=mock_document_repository,
        )

    assert searcher._document_processor is mock_document_processor
    assert searcher._document_repository is mock_document_repository
    assert searcher.brave_api_key == "test_api_key"


def test_web_searcher_initialization_without_api_key(
    mock_document_processor, mock_document_repository
):
    """Test WebSearcher initialization when no Brave API key is configured."""
    with patch("src.components.retrieval.web_searcher.settings") as mock_settings:
        mock_settings.web.BRAVE_SEARCH_API_KEY = None

        searcher = WebSearcher(
            document_processor=mock_document_processor,
            document_repository=mock_document_repository,
        )

    assert searcher.brave_api_key is None


# ==================== _search_web TESTS ====================


def test_search_web_success(web_searcher):
    """Test successful web search via the Brave Search API."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "web": {
            "results": [
                {
                    "title": "Python Tutorial",
                    "description": "Learn Python programming",
                    "url": "https://example.com/python",
                },
                {
                    "title": "Advanced Python",
                    "description": "Advanced Python concepts",
                    "url": "https://example.com/advanced",
                },
            ]
        }
    }
    mock_response.raise_for_status = Mock()

    with patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.return_value = mock_response
        mock_settings.web.MAX_WEB_SEARCH_RESULTS = 10
        mock_settings.web.WEB_REQUEST_TIMEOUT_SECS = 10

        results = web_searcher._search_web("python programming")

    assert len(results) == 2
    assert isinstance(results[0], WebSearchResult)
    assert results[0].title == "Python Tutorial"
    assert results[0].url == "https://example.com/python"
    assert results[0].snippet == "Learn Python programming"
    call_headers = mock_get.call_args.kwargs["headers"]
    assert call_headers["X-Subscription-Token"] == "test_api_key"


def test_search_web_no_results_falls_through_empty(web_searcher):
    """Test web search returns an empty list when the API response has no results."""
    mock_response = Mock()
    mock_response.json.return_value = {}
    mock_response.raise_for_status = Mock()

    with patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.return_value = mock_response
        mock_settings.web.MAX_WEB_SEARCH_RESULTS = 10
        mock_settings.web.WEB_REQUEST_TIMEOUT_SECS = 10

        results = web_searcher._search_web("test query")

    assert results == []


def test_search_web_missing_api_credentials_uses_fallback(web_searcher):
    """Test web search uses the fallback when no Brave API key is configured."""
    web_searcher.brave_api_key = None

    with patch.object(web_searcher, "_fallback_search") as mock_fallback, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_fallback.return_value = []
        mock_settings.web.MAX_WEB_SEARCH_RESULTS = 10

        web_searcher._search_web("test query")

    mock_fallback.assert_called_once()


def test_search_web_request_error_falls_back(web_searcher):
    """Test web search falls back to DuckDuckGo when the Brave API request fails."""
    with patch(
        "src.components.retrieval.web_searcher.requests.get"
    ) as mock_get, patch.object(
        web_searcher, "_fallback_search"
    ) as mock_fallback, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.side_effect = requests.RequestException("API Error")
        mock_fallback.return_value = []
        mock_settings.web.MAX_WEB_SEARCH_RESULTS = 10
        mock_settings.web.WEB_REQUEST_TIMEOUT_SECS = 10

        results = web_searcher._search_web("test query")

    mock_fallback.assert_called_once()
    assert results == []


# ==================== _fallback_search TESTS ====================


def test_fallback_search_disabled(web_searcher):
    """Test fallback search returns nothing when disabled via settings."""
    with patch("src.components.retrieval.web_searcher.settings") as mock_settings:
        mock_settings.web.WEB_SEARCH_FALLBACK_ENABLED = False

        results = web_searcher._fallback_search("test query", 5)

    assert results == []


def test_fallback_search_success(web_searcher):
    """Test successful fallback search using ddgs (DuckDuckGo)."""
    ddgs_results = [
        {"title": "Result 1", "body": "Snippet 1", "href": "https://example.com/1"},
        {"title": "Result 2", "body": "Snippet 2", "href": "https://example.com/2"},
    ]

    with patch(
        "src.components.retrieval.web_searcher.DDGS"
    ) as mock_ddgs_cls, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_settings.web.WEB_SEARCH_FALLBACK_ENABLED = True
        mock_ddgs_cls.return_value.text.return_value = ddgs_results

        results = web_searcher._fallback_search("test query", 5)

    assert len(results) == 2
    assert results[0] == WebSearchResult(
        title="Result 1", snippet="Snippet 1", url="https://example.com/1"
    )


def test_fallback_search_ddgs_exception_returns_empty(web_searcher):
    """Test fallback search handles ddgs-specific exceptions gracefully."""
    with patch(
        "src.components.retrieval.web_searcher.DDGS"
    ) as mock_ddgs_cls, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_settings.web.WEB_SEARCH_FALLBACK_ENABLED = True
        mock_ddgs_cls.return_value.text.side_effect = DDGSException("rate limited")

        results = web_searcher._fallback_search("test query", 5)

    assert results == []


# ==================== _fetch_content TESTS ====================


def test_fetch_content_returns_page_html_when_long_enough(web_searcher):
    """Test that real page HTML is used when it meets the minimum length."""
    result = WebSearchResult(title="Title", snippet="Snippet", url="https://example.com")

    with patch.object(
        web_searcher, "_fetch_page_html", return_value="<html>" + "x" * 100 + "</html>"
    ), patch("src.components.retrieval.web_searcher.settings") as mock_settings:
        mock_settings.app.MIN_DOCUMENT_CONTENT_LENGTH = 20

        content = web_searcher._fetch_content(result)

    assert content == "<html>" + "x" * 100 + "</html>"


def test_fetch_content_falls_back_to_title_snippet_when_too_short(web_searcher):
    """Test that a minimal HTML wrapper is built from the title/snippet when
    the fetched page content is too short (or missing)."""
    result = WebSearchResult(
        title="Test Article", snippet="A short summary", url="https://example.com"
    )

    with patch.object(
        web_searcher, "_fetch_page_html", return_value="short"
    ), patch("src.components.retrieval.web_searcher.settings") as mock_settings:
        mock_settings.app.MIN_DOCUMENT_CONTENT_LENGTH = 100

        content = web_searcher._fetch_content(result)

    assert content == (
        "<html><body><h1>Test Article</h1><p>A short summary</p></body></html>"
    )


def test_fetch_content_escapes_html_in_fallback(web_searcher):
    """Test that title/snippet HTML-injection attempts are escaped in the fallback."""
    result = WebSearchResult(
        title="<script>alert(1)</script>",
        snippet="ok",
        url="https://example.com",
    )

    with patch.object(
        web_searcher, "_fetch_page_html", return_value=None
    ), patch("src.components.retrieval.web_searcher.settings") as mock_settings:
        mock_settings.app.MIN_DOCUMENT_CONTENT_LENGTH = 20

        content = web_searcher._fetch_content(result)

    assert "<script>" not in content
    assert "&lt;script&gt;" in content


def test_fetch_content_returns_none_on_exception(web_searcher):
    """Test that an exception while fetching content is swallowed and returns None."""
    result = WebSearchResult(title="Title", snippet="Snippet", url="https://example.com")

    with patch.object(
        web_searcher, "_fetch_page_html", side_effect=Exception("boom")
    ):
        content = web_searcher._fetch_content(result)

    assert content is None


# ==================== _is_safe_url TESTS (SSRF protection) ====================


def test_is_safe_url_blocks_loopback_address(web_searcher):
    """Test that loopback addresses are blocked."""
    assert web_searcher._is_safe_url("http://127.0.0.1/") is False


def test_is_safe_url_blocks_private_address(web_searcher):
    """Test that private network addresses are blocked."""
    assert web_searcher._is_safe_url("http://192.168.1.1/") is False


def test_is_safe_url_blocks_missing_hostname(web_searcher):
    """Test that a URL with no parseable hostname is treated as unsafe."""
    assert web_searcher._is_safe_url("not-a-url") is False


def test_is_safe_url_blocks_unresolvable_hostname(web_searcher):
    """Test that a hostname that cannot be resolved is treated as unsafe."""
    assert web_searcher._is_safe_url("http://this-host-does-not-exist.invalid/") is False


def test_is_safe_url_allows_public_domain(web_searcher):
    """Test that a real public domain is treated as safe (real DNS resolution)."""
    assert web_searcher._is_safe_url("https://example.com") is True


# ==================== _fetch_page_html TESTS ====================


def test_fetch_page_html_success(web_searcher):
    """Test successful raw HTML fetch for a safe URL."""
    mock_response = Mock()
    mock_response.text = "<html>page content</html>"
    mock_response.headers = {"Content-Type": "text/html; charset=utf-8"}
    mock_response.raise_for_status = Mock()

    with patch.object(
        web_searcher, "_is_safe_url", return_value=True
    ), patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.return_value = mock_response
        mock_settings.web.WEB_USER_AGENT = "test-agent"
        mock_settings.web.WEB_REQUEST_TIMEOUT_SECS = 10

        content = web_searcher._fetch_page_html("https://example.com")

    assert content == "<html>page content</html>"


def test_fetch_page_html_rejects_non_html_content(web_searcher):
    """Test that a non-HTML Content-Type is rejected rather than treated as HTML."""
    mock_response = Mock()
    mock_response.text = "%PDF-1.4 not html"
    mock_response.headers = {"Content-Type": "application/pdf"}
    mock_response.raise_for_status = Mock()

    with patch.object(
        web_searcher, "_is_safe_url", return_value=True
    ), patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.return_value = mock_response
        mock_settings.web.WEB_USER_AGENT = "test-agent"
        mock_settings.web.WEB_REQUEST_TIMEOUT_SECS = 10

        content = web_searcher._fetch_page_html("https://example.com/file.pdf")

    assert content is None


def test_fetch_page_html_blocked_for_unsafe_url(web_searcher):
    """Test that fetching is skipped entirely (no request made) for an unsafe URL."""
    with patch.object(
        web_searcher, "_is_safe_url", return_value=False
    ), patch("src.components.retrieval.web_searcher.requests.get") as mock_get:
        content = web_searcher._fetch_page_html("http://127.0.0.1/admin")

    mock_get.assert_not_called()
    assert content is None


def test_fetch_page_html_request_error_returns_none(web_searcher):
    """Test that a request failure is handled gracefully."""
    with patch.object(
        web_searcher, "_is_safe_url", return_value=True
    ), patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.side_effect = requests.RequestException("network error")
        mock_settings.web.WEB_USER_AGENT = "test-agent"
        mock_settings.web.WEB_REQUEST_TIMEOUT_SECS = 10

        content = web_searcher._fetch_page_html("https://example.com")

    assert content is None


# ==================== search_and_retrieve_web_content TESTS ====================


def test_search_and_retrieve_web_content_empty_query_returns_empty(web_searcher):
    """Test that an empty query short-circuits without searching."""
    assert web_searcher.search_and_retrieve_web_content("") == []
    assert web_searcher.search_and_retrieve_web_content("   ") == []


def test_search_and_retrieve_web_content_no_search_results(web_searcher):
    """Test that no search results yields no web content."""
    with patch.object(web_searcher, "_search_web", return_value=[]):
        results = web_searcher.search_and_retrieve_web_content("obscure query")

    assert results == []


def test_search_and_retrieve_web_content_skips_invalid_urls(web_searcher):
    """Test that results with non-http(s) URLs are skipped."""
    search_results = [
        WebSearchResult(title="FTP", snippet="Test", url="ftp://invalid.com"),
        WebSearchResult(title="Empty", snippet="Test", url=""),
    ]

    with patch.object(web_searcher, "_search_web", return_value=search_results):
        results = web_searcher.search_and_retrieve_web_content("query")

    assert results == []


def test_search_and_retrieve_web_content_success(web_searcher):
    """Test that valid results are fetched and wrapped as WebContent."""
    search_results = [
        WebSearchResult(title="Doc1", snippet="Test1", url="https://example1.com"),
        WebSearchResult(title="Doc2", snippet="Test2", url="https://example2.com"),
    ]

    with patch.object(
        web_searcher, "_search_web", return_value=search_results
    ), patch.object(
        web_searcher, "_fetch_content", return_value="<html>content</html>"
    ), patch(
        "src.components.retrieval.web_searcher.time.sleep"
    ) as mock_sleep, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_settings.web.WEB_REQUEST_DELAY_SECS = 0.5

        results = web_searcher.search_and_retrieve_web_content("query")

    assert len(results) == 2
    assert all(isinstance(r, WebContent) for r in results)
    assert results[0].source == "https://example1.com"
    # Rate limiting: sleep once, between the first and second request only.
    mock_sleep.assert_called_once_with(0.5)


def test_search_and_retrieve_web_content_continues_after_fetch_error(web_searcher):
    """Test that an error fetching one result doesn't stop the others."""
    search_results = [
        WebSearchResult(title="Doc1", snippet="Test1", url="https://example1.com"),
        WebSearchResult(title="Doc2", snippet="Test2", url="https://example2.com"),
    ]

    def fetch_side_effect(result):
        if "1" in result.url:
            raise Exception("fetch failed")
        return "<html>ok</html>"

    with patch.object(
        web_searcher, "_search_web", return_value=search_results
    ), patch.object(
        web_searcher, "_fetch_content", side_effect=fetch_side_effect
    ), patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_settings.web.WEB_REQUEST_DELAY_SECS = 0

        results = web_searcher.search_and_retrieve_web_content("query")

    assert len(results) == 1
    assert results[0].source == "https://example2.com"


def test_search_and_retrieve_web_content_critical_error_returns_empty(web_searcher):
    """Test that an unexpected error during search is handled gracefully."""
    with patch.object(
        web_searcher, "_search_web", side_effect=Exception("critical failure")
    ):
        results = web_searcher.search_and_retrieve_web_content("query")

    assert results == []


# ==================== ingest_web_content TESTS ====================


@pytest.mark.asyncio
async def test_ingest_web_content_no_content_returns_zero(web_searcher, mock_tx):
    """Test that ingestion is a no-op when no web content is retrieved."""
    chat_session_id = uuid4()

    with patch.object(
        web_searcher, "search_and_retrieve_web_content", return_value=[]
    ):
        result = await web_searcher.ingest_web_content("query", chat_session_id, tx=mock_tx)

    assert result == 0
    web_searcher._document_repository.create.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_web_content_success_sums_saved_chunks(web_searcher, mock_tx):
    """Test that each piece of web content is staged as a Document and its
    chunks are saved (flushed, not committed) within the given tx, with the
    total summed across all content."""
    chat_session_id = uuid4()
    web_contents = [
        WebContent(content="Content from source 1", source="https://example.com/1"),
        WebContent(content="Content from source 2", source="https://example.com/2"),
    ]

    web_searcher._document_processor.save_document_chunks = AsyncMock(
        side_effect=[3, 2]
    )

    with patch.object(
        web_searcher, "search_and_retrieve_web_content", return_value=web_contents
    ):
        result = await web_searcher.ingest_web_content("query", chat_session_id, tx=mock_tx)

    assert result == 5
    assert web_searcher._document_repository.create.call_count == 2
    for call in web_searcher._document_repository.create.call_args_list:
        assert call.kwargs["tx"] is mock_tx
    mock_tx.commit.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_web_content_saves_exact_source_url_as_source(web_searcher, mock_tx):
    """Test that the Document's source is the exact source URL (plus
    .html), not a hashed/sanitized version - so the origin is preserved."""
    chat_session_id = uuid4()
    web_contents = [
        WebContent(content="Some content", source="https://en.wikipedia.org/wiki/London"),
    ]
    web_searcher._document_processor.save_document_chunks = AsyncMock(return_value=1)

    with patch.object(
        web_searcher, "search_and_retrieve_web_content", return_value=web_contents
    ):
        await web_searcher.ingest_web_content("query", chat_session_id, tx=mock_tx)

    saved_document = web_searcher._document_repository.create.call_args.kwargs["data"]
    assert saved_document.source == "https://en.wikipedia.org/wiki/London.html"


@pytest.mark.asyncio
async def test_ingest_web_content_marks_document_as_web_search_source_type(
    web_searcher, mock_tx
):
    """Test that documents created from web ingestion are tagged
    WEB_SEARCH, distinguishing them from uploaded documents."""
    from src.config.constants import DocumentSourceType

    chat_session_id = uuid4()
    web_contents = [
        WebContent(content="Some content", source="https://example.com/a"),
    ]
    web_searcher._document_processor.save_document_chunks = AsyncMock(return_value=1)

    with patch.object(
        web_searcher, "search_and_retrieve_web_content", return_value=web_contents
    ):
        await web_searcher.ingest_web_content("query", chat_session_id, tx=mock_tx)

    saved_document = web_searcher._document_repository.create.call_args.kwargs["data"]
    assert saved_document.source_type == DocumentSourceType.WEB_SEARCH


@pytest.mark.asyncio
async def test_ingest_web_content_skips_content_over_per_document_limit(web_searcher, mock_tx):
    """Test that a single piece of web content larger than MAX_FILE_SIZE_MB
    is skipped rather than saved, mirroring the upload size limit."""
    from src.config.configs import settings

    chat_session_id = uuid4()
    oversized_content = "a" * (int(settings.files.MAX_FILE_SIZE_MB * 1024 * 1024) + 1)
    web_contents = [
        WebContent(content=oversized_content, source="https://example.com/big"),
    ]

    with patch.object(
        web_searcher, "search_and_retrieve_web_content", return_value=web_contents
    ):
        result = await web_searcher.ingest_web_content("query", chat_session_id, tx=mock_tx)

    assert result == 0
    web_searcher._document_repository.create.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_web_content_skips_when_chat_storage_quota_exceeded(web_searcher, mock_tx):
    """Test that content is skipped when it would push the chat's total
    document storage over MAX_FILES_PER_CHAT_MB, even if the content itself
    is under the per-document limit."""
    from src.config.configs import settings

    chat_session_id = uuid4()
    web_contents = [
        WebContent(content="small content", source="https://example.com/1"),
    ]

    web_searcher._document_repository.get_total_size_mb = AsyncMock(
        return_value=settings.files.MAX_FILES_PER_CHAT_MB
    )

    with patch.object(
        web_searcher, "search_and_retrieve_web_content", return_value=web_contents
    ):
        result = await web_searcher.ingest_web_content("query", chat_session_id, tx=mock_tx)

    assert result == 0
    web_searcher._document_repository.create.assert_not_called()


# ==================== _clean_web_text TESTS ====================


def test_clean_web_text_replaces_literal_escape_sequences():
    """Test that literal backslash-n/backslash-t two-character sequences are
    replaced with a space, not treated as real whitespace."""
    result = _clean_web_text("line1\\nline2\\tindented")

    assert result == "line1 line2 indented"


def test_clean_web_text_preserves_real_whitespace_structure():
    """Test that a real newline (as would appear in the `Source: name\\n\\n...`
    chunk prefix) is left untouched, since it's a single real character, not
    the two-character literal sequence being targeted."""
    result = _clean_web_text("Source: page.html\n\nActual body text")

    assert result == "Source: page.html\n\nActual body text"


def test_clean_web_text_collapses_repeated_whitespace():
    """Test that repeated spaces left behind by escape-sequence replacement
    are collapsed to a single space."""
    result = _clean_web_text("a\\n\\n\\nb")

    assert result == "a b"


def test_clean_web_text_strips_leading_and_trailing_whitespace():
    result = _clean_web_text("\\n  leading and trailing  \\t")

    assert result == "leading and trailing"


@pytest.mark.asyncio
async def test_ingest_web_content_sanitizes_chunks_before_saving(web_searcher, mock_tx):
    """Test that chunk text is cleaned of literal escape sequences before
    being handed to save_document_chunks."""
    chat_session_id = uuid4()
    web_contents = [
        WebContent(content="Some content", source="https://example.com/a"),
    ]
    web_searcher._document_processor.chunk.return_value = ["line1\\nline2"]
    web_searcher._document_processor.save_document_chunks = AsyncMock(return_value=1)

    with patch.object(
        web_searcher, "search_and_retrieve_web_content", return_value=web_contents
    ):
        await web_searcher.ingest_web_content("query", chat_session_id, tx=mock_tx)

    saved_chunks = web_searcher._document_processor.save_document_chunks.call_args.kwargs[
        "chunks"
    ]
    assert saved_chunks == ["line1 line2"]


# ==================== DATACLASS TESTS ====================


def test_web_content_creation():
    """Test WebContent dataclass creation."""
    content = WebContent(content="Test content", source="https://example.com")

    assert content.content == "Test content"
    assert content.source == "https://example.com"


def test_web_search_result_creation():
    """Test WebSearchResult dataclass creation."""
    result = WebSearchResult(
        title="Test Title",
        snippet="Test snippet",
        url="https://example.com",
    )

    assert result.title == "Test Title"
    assert result.snippet == "Test snippet"
    assert result.url == "https://example.com"
