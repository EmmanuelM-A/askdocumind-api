"""
Unit tests for the WebSearcher component.
Tests web search, content retrieval, and document ingestion functionality.
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
import requests

from src.components.retrieval.web_searcher import (
    WebSearcher,
    WebContent,
    WebSearchResult,
)

# ==================== INITIALIZATION TESTS ====================


def test_web_searcher_initialization(mock_embedder, mock_vector_processor):
    """Test successful WebSearcher initialization with mocked dependencies."""
    with patch("src.components.retrieval.web_searcher.settings") as mock_settings:
        mock_settings.web.SEARCH_API_KEY.get_secret_value.return_value = "test_api_key"
        mock_settings.web.SEARCH_ENGINE_ID.get_secret_value.return_value = (
            "test_engine_id"
        )

        searcher = WebSearcher(
            embedder=mock_embedder,
            vector_processor=mock_vector_processor,
        )

        assert searcher.embedder is mock_embedder
        assert searcher._vector_processor is mock_vector_processor
        assert searcher.search_api_key == "test_api_key"
        assert searcher.search_engine_id == "test_engine_id"


def test_web_searcher_initialization_with_empty_credentials(
    mock_embedder, mock_vector_processor
):
    """Test WebSearcher initialization handles empty API credentials."""
    with patch("src.components.retrieval.web_searcher.settings") as mock_settings:
        mock_settings.web.SEARCH_API_KEY.get_secret_value.return_value = ""
        mock_settings.web.SEARCH_ENGINE_ID.get_secret_value.return_value = ""

        searcher = WebSearcher(
            embedder=mock_embedder,
            vector_processor=mock_vector_processor,
        )

        assert searcher.search_api_key == ""
        assert searcher.search_engine_id == ""


# ==================== SEARCH AND INGEST WEB CONTENT TESTS ====================


# ==================== WEB SEARCH TESTS ====================


def test_search_web_success(web_searcher):
    """Test successful web search with Google Custom Search API."""
    query = "python programming"

    mock_response = Mock()
    mock_response.json.return_value = {
        "items": [
            {
                "title": "Python Tutorial",
                "snippet": "Learn Python programming",
                "url": "https://example.com/python",
            },
            {
                "title": "Advanced Python",
                "snippet": "Advanced Python concepts",
                "url": "https://example.com/advanced",
            },
        ]
    }
    mock_response.raise_for_status = Mock()

    with patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.return_value = mock_response
        mock_settings.web.MAX_WEB_SEARCH_RESULTS = 10
        mock_settings.web.MAX_WEB_REQUEST_RESULTS = 10
        mock_settings.web.WEB_REQUEST_TIMEOUT_SECS = 10

        results = web_searcher._search_web(query)

    assert len(results) == 2
    assert isinstance(results[0], WebSearchResult)
    assert results[0].title == "Python Tutorial"
    assert results[0].url == "https://example.com/python"
    assert results[0].snippet == "Learn Python programming"


def test_search_web_no_items_in_response(web_searcher):
    """Test web search when API returns response without items."""
    query = "test query"

    mock_response = Mock()
    mock_response.json.return_value = {}  # No 'items' key
    mock_response.raise_for_status = Mock()

    with patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.return_value = mock_response
        mock_settings.web.MAX_WEB_SEARCH_RESULTS = 10
        mock_settings.web.MAX_WEB_REQUEST_RESULTS = 10
        mock_settings.web.WEB_REQUEST_TIMEOUT_SECS = 10

        results = web_searcher._search_web(query)

    assert results == []


def test_search_web_api_error_fallback(web_searcher):
    """Test web search falls back to fallback search on API error."""
    query = "test query"

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
        mock_settings.web.MAX_WEB_REQUEST_RESULTS = 10
        mock_settings.web.WEB_REQUEST_TIMEOUT_SECS = 10

        results = web_searcher._search_web(query)

    mock_fallback.assert_called_once()
    assert results == []


def test_search_web_missing_api_credentials_uses_fallback(web_searcher):
    """Test web search uses fallback when API credentials are missing."""
    query = "test query"

    # Set credentials to empty
    web_searcher.search_api_key = ""
    web_searcher.search_engine_id = ""

    with patch.object(web_searcher, "_fallback_search") as mock_fallback, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_fallback.return_value = []
        mock_settings.web.MAX_WEB_SEARCH_RESULTS = 10

        web_searcher._search_web(query)

    mock_fallback.assert_called_once()


# ==================== FALLBACK SEARCH TESTS ====================


def test_fallback_search_disabled(web_searcher):
    """Test fallback search returns empty when disabled."""
    query = "test query"

    with patch("src.components.retrieval.web_searcher.settings") as mock_settings:
        mock_settings.web.WEB_SEARCH_FALLBACK_ENABLED = False

        results = web_searcher._fallback_search(query, 5)

    assert results == []


def test_fallback_search_success(web_searcher):
    """Test successful fallback search from DuckDuckGo."""
    query = "test query"

    mock_html = """
    <html>
        <div class="result">
            <a class="result__a" href="https://example.com/1">Example Title 1</a>
            <div class="result__snippet">Example snippet 1</div>
        </div>
        <div class="result">
            <a class="result__a" href="https://example.com/2">Example Title 2</a>
            <div class="result__snippet">Example snippet 2</div>
        </div>
    </html>
    """

    mock_response = Mock()
    mock_response.content = mock_html.encode()
    mock_response.raise_for_status = Mock()

    with patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.return_value = mock_response
        mock_settings.web.WEB_SEARCH_FALLBACK_ENABLED = True
        mock_settings.web.WEB_USER_AGENT = "test-agent"

        results = web_searcher._fallback_search(query, 5)

    assert len(results) >= 1
    assert all(isinstance(r, WebSearchResult) for r in results)


def test_fallback_search_request_error(web_searcher):
    """Test fallback search handles request errors gracefully."""
    query = "test query"

    with patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.side_effect = requests.RequestException("Network error")
        mock_settings.web.WEB_SEARCH_FALLBACK_ENABLED = True
        mock_settings.web.WEB_USER_AGENT = "test-agent"

        results = web_searcher._fallback_search(query, 5)

    assert results == []


# ==================== FETCH AND FULL CONTENT TESTS ====================


def test_fetch_and_full_content_success(web_searcher):
    """Test successfully fetching full content from a web result."""
    result = WebSearchResult(
        title="Test Article",
        snippet="This is a test article",
        url="https://example.com/article",
    )

    mock_page_content = "Full page content with lots of information"

    with patch.object(web_searcher, "_fetch_page_content") as mock_fetch, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_fetch.return_value = mock_page_content
        mock_settings.app.MIN_DOCUMENT_CONTENT_LENGTH = 10

        content = web_searcher._fetch_and_full_content(result)

    assert content is not None
    assert "Test Article" in content
    assert "This is a test article" in content
    assert mock_page_content in content


def test_fetch_and_full_content_short_content_uses_snippet(web_searcher):
    """Test document uses snippet when fetched content is too short."""
    result = WebSearchResult(
        title="Test Article",
        snippet="This is a test article snippet",
        url="https://example.com/article",
    )

    with patch.object(web_searcher, "_fetch_page_content") as mock_fetch, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_fetch.return_value = "Short"  # Too short
        mock_settings.app.MIN_DOCUMENT_CONTENT_LENGTH = 100

        content = web_searcher._fetch_and_full_content(result)

    assert content is not None
    assert "Summary" in content
    assert "This is a test article snippet" in content
    assert "Short" not in content  # Should not include the short content


def test_fetch_and_full_content_fetch_fails(web_searcher):
    """Test document creation when content fetch returns None."""
    result = WebSearchResult(
        title="Test Article",
        snippet="This is a test article",
        url="https://example.com/article",
    )

    with patch.object(web_searcher, "_fetch_page_content") as mock_fetch, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_fetch.return_value = None
        mock_settings.web.MIN_WEB_CONTENT_LENGTH = 10

        content = web_searcher._fetch_and_full_content(result)

    assert content is not None
    # Should still create content with snippet
    assert "Summary" in content
    assert "This is a test article" in content


def test_fetch_and_full_content_error_handling(web_searcher):
    """Test content fetching handles exceptions gracefully."""
    result = WebSearchResult(
        title="Test Article",
        snippet="Test",
        url="https://example.com/article",
    )

    with patch.object(web_searcher, "_fetch_page_content") as mock_fetch:
        mock_fetch.side_effect = Exception("Fetch error")

        content = web_searcher._fetch_and_full_content(result)

    assert content is None


# ==================== FETCH PAGE CONTENT TESTS ====================


def test_fetch_page_content_success(web_searcher):
    """Test successful page content fetching with HTML parsing."""
    url = "https://example.com/article"

    mock_html = """
    <html>
        <body>
            <article>
                <p>This is the main content.</p>
                <p>More content here.</p>
            </article>
        </body>
    </html>
    """

    mock_response = Mock()
    mock_response.content = mock_html.encode()
    mock_response.raise_for_status = Mock()

    with patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.return_value = mock_response
        mock_settings.web.WEB_USER_AGENT = "test-agent"
        mock_settings.web.WEB_REQUEST_TIMEOUT_SECS = 10

        content = web_searcher._fetch_page_content(url)

    assert content is not None
    assert "main content" in content
    assert len(content) > 0


def test_fetch_page_content_removes_unwanted_elements(web_searcher):
    """Test that scripts, styles, and nav elements are removed from content."""
    url = "https://example.com/article"

    mock_html = """
    <html>
        <head>
            <script>alert('remove me');</script>
            <style>.hidden { display: none; }</style>
        </head>
        <body>
            <nav>Navigation</nav>
            <article>
                <p>Keep this content.</p>
            </article>
            <footer>Footer content</footer>
        </body>
    </html>
    """

    mock_response = Mock()
    mock_response.content = mock_html.encode()
    mock_response.raise_for_status = Mock()

    with patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.return_value = mock_response
        mock_settings.web.WEB_USER_AGENT = "test-agent"
        mock_settings.web.WEB_REQUEST_TIMEOUT_SECS = 10

        content = web_searcher._fetch_page_content(url)

    assert "alert" not in content
    assert "display: none" not in content
    assert "Keep this content" in content


def test_fetch_page_content_request_error(web_searcher):
    """Test page content fetch handles request exceptions."""
    url = "https://example.com/article"

    with patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.side_effect = requests.RequestException("Network error")
        mock_settings.web.WEB_USER_AGENT = "test-agent"
        mock_settings.web.WEB_REQUEST_TIMEOUT_SECS = 10

        content = web_searcher._fetch_page_content(url)

    assert content is None


def test_fetch_page_content_with_body_fallback(web_searcher):
    """Test content extraction falls back to body when no article found."""
    url = "https://example.com/article"

    mock_html = """
    <html>
        <body>
            <div>Some body content here</div>
        </body>
    </html>
    """

    mock_response = Mock()
    mock_response.content = mock_html.encode()
    mock_response.raise_for_status = Mock()

    with patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.return_value = mock_response
        mock_settings.web.WEB_USER_AGENT = "test-agent"
        mock_settings.web.WEB_REQUEST_TIMEOUT_SECS = 10

        content = web_searcher._fetch_page_content(url)

    assert content is not None
    assert "body content" in content


# ==================== SEARCH AND INGEST TESTS ====================


@pytest.mark.asyncio
async def test_search_and_ingest_web_content_success(web_searcher):
    """Test successfully searching for web content and ingesting it."""
    query = "test query"
    chat_session_id = uuid4()
    tx = Mock()

    # Mock the web content retrieval
    web_content = [
        WebContent(content="Content from source 1", source="https://example.com/1"),
        WebContent(content="Content from source 2", source="https://example.com/2"),
    ]

    with patch.object(
        web_searcher, "_search_and_retrieve_content_from_web"
    ) as mock_retrieve:
        mock_retrieve.return_value = web_content
        web_searcher._vector_processor.process_and_save_vectors_from_web = AsyncMock(
            return_value=5
        )

        result = await web_searcher.search_and_ingest_web_content(
            query, chat_session_id, tx
        )

    assert result == 5
    web_searcher._vector_processor.process_and_save_vectors_from_web.assert_called_once()
    call_kwargs = (
        web_searcher._vector_processor.process_and_save_vectors_from_web.call_args.kwargs
    )
    assert call_kwargs["chat_session_id"] == chat_session_id
    assert len(call_kwargs["raw_web_contents"]) == 2
    assert call_kwargs["tx"] is tx


@pytest.mark.asyncio
async def test_search_and_ingest_web_content_no_results(web_searcher):
    """Test web ingestion returns 0 when no content retrieved."""
    query = "test query"
    chat_session_id = uuid4()
    tx = Mock()

    with patch.object(
        web_searcher, "_search_and_retrieve_content_from_web"
    ) as mock_retrieve:
        mock_retrieve.return_value = []

        result = await web_searcher.search_and_ingest_web_content(
            query, chat_session_id, tx
        )

    assert result == 0
    web_searcher._vector_processor.process_and_save_vectors_from_web.assert_not_called()


# ==================== SEARCH AND RETRIEVE CONTENT TESTS ====================


def test_search_and_retrieve_content_empty_query(web_searcher):
    """Test search with empty query returns empty list."""
    results = web_searcher._search_and_retrieve_content_from_web("")

    assert results == []


def test_search_and_retrieve_content_whitespace_only_query(web_searcher):
    """Test search with whitespace-only query returns empty list."""
    results = web_searcher._search_and_retrieve_content_from_web("   ")

    assert results == []


def test_search_and_retrieve_content_no_search_results(web_searcher):
    """Test search handling when web search returns no results."""
    query = "some obscure query"

    with patch.object(web_searcher, "_search_web") as mock_search:
        mock_search.return_value = []

        results = web_searcher._search_and_retrieve_content_from_web(query)

    assert results == []


def test_search_and_retrieve_content_invalid_urls(web_searcher):
    """Test search skips results with invalid URLs."""
    query = "test query"

    search_results = [
        WebSearchResult(title="Invalid URL", snippet="Test", url="not-a-url"),
        WebSearchResult(title="FTP URL", snippet="Test", url="ftp://invalid.com"),
    ]

    with patch.object(web_searcher, "_search_web") as mock_search:
        mock_search.return_value = search_results

        results = web_searcher._search_and_retrieve_content_from_web(query)

    assert len(results) == 0


def test_search_and_retrieve_content_mixed_valid_invalid_urls(web_searcher):
    """Test search processes valid URLs and skips invalid ones."""
    query = "test query"

    search_results = [
        WebSearchResult(title="Invalid", snippet="Test", url="not-a-url"),  # Invalid
        WebSearchResult(
            title="Valid 1",
            snippet="Test",
            url="https://example.com/1",
        ),  # Valid
        WebSearchResult(
            title="FTP URL", snippet="Test", url="ftp://invalid.com"
        ),  # Invalid
        WebSearchResult(
            title="Valid 2",
            snippet="Test",
            url="https://example.com/2",
        ),  # Valid
    ]

    with patch.object(web_searcher, "_search_web") as mock_search, patch.object(
        web_searcher, "_fetch_and_full_content"
    ) as mock_fetch, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_search.return_value = search_results
        mock_fetch.return_value = "Valid content"
        mock_settings.web.WEB_REQUEST_DELAY_SECS = 0

        results = web_searcher._search_and_retrieve_content_from_web(query)

    # Should only process the 2 valid URLs
    assert len(results) == 2
    assert all(isinstance(r, WebContent) for r in results)


def test_search_and_retrieve_content_rate_limiting(web_searcher):
    """Test search respects rate limiting delays between requests."""
    query = "test query"

    search_results = [
        WebSearchResult(
            title="Doc1",
            snippet="Test1",
            url="https://example1.com",
        ),
        WebSearchResult(
            title="Doc2",
            snippet="Test2",
            url="https://example2.com",
        ),
    ]

    with patch.object(web_searcher, "_search_web") as mock_search, patch.object(
        web_searcher, "_fetch_and_full_content"
    ) as mock_fetch, patch(
        "src.components.retrieval.web_searcher.time.sleep"
    ) as mock_sleep, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_search.return_value = search_results
        mock_fetch.return_value = "Content"
        mock_settings.web.WEB_REQUEST_DELAY_SECS = 0.5

        web_searcher._search_and_retrieve_content_from_web(query)

    # Should sleep once between first and second request
    assert mock_sleep.call_count == 1
    mock_sleep.assert_called_with(0.5)


def test_search_and_retrieve_content_fetch_error_continues(web_searcher):
    """Test search continues processing after fetch error on one result."""
    query = "test query"

    search_results = [
        WebSearchResult(
            title="Doc1",
            snippet="Test1",
            url="https://example1.com",
        ),
        WebSearchResult(
            title="Doc2",
            snippet="Test2",
            url="https://example2.com",
        ),
        WebSearchResult(
            title="Doc3",
            snippet="Test3",
            url="https://example3.com",
        ),
    ]

    def fetch_side_effect(result):
        if "2" in result.url:
            raise Exception("Fetch error")
        return f"Content from {result.url}"

    with patch.object(web_searcher, "_search_web") as mock_search, patch.object(
        web_searcher, "_fetch_and_full_content"
    ) as mock_fetch, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_search.return_value = search_results
        mock_fetch.side_effect = fetch_side_effect
        mock_settings.web.WEB_REQUEST_DELAY_SECS = 0

        results = web_searcher._search_and_retrieve_content_from_web(query)

    # Should process 2 out of 3 (skip the one that errored)
    assert len(results) == 2


def test_search_and_retrieve_content_all_fetch_errors(web_searcher):
    """Test search handles case where all fetches fail."""
    query = "test query"

    search_results = [
        WebSearchResult(
            title="Doc1",
            snippet="Test1",
            url="https://example1.com",
        ),
        WebSearchResult(
            title="Doc2",
            snippet="Test2",
            url="https://example2.com",
        ),
    ]

    with patch.object(web_searcher, "_search_web") as mock_search, patch.object(
        web_searcher, "_fetch_and_full_content"
    ) as mock_fetch, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_search.return_value = search_results
        mock_fetch.return_value = None  # All fetches fail
        mock_settings.web.WEB_REQUEST_DELAY_SECS = 0

        results = web_searcher._search_and_retrieve_content_from_web(query)

    # Should return empty when all fetches fail
    assert len(results) == 0


def test_search_and_retrieve_content_critical_error(web_searcher):
    """Test search handles critical errors gracefully."""
    query = "test query"

    with patch.object(web_searcher, "_search_web") as mock_search, patch.object(
        web_searcher, "_logger"
    ) as _:
        mock_search.side_effect = Exception("Critical error")

        results = web_searcher._search_and_retrieve_content_from_web(query)

    assert results == []


# ==================== WEB CONTENT AND RESULT DATACLASS TESTS ====================


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
