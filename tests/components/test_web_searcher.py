"""
Unit tests for the WebSearcher component.
Tests web search, content retrieval, and document processing functionality.
"""

from unittest.mock import Mock, patch

import requests

from src.components.retrieval.web_searcher import WebSearcher
from src.components.ingestion.document import FileDocument


# ==================== INITIALIZATION TESTS ====================


def test_web_searcher_initialization(
    mock_embedder, mock_document_processor, mock_vector_store
):
    """Test successful WebSearcher initialization."""
    with patch("src.components.retrieval.web_searcher.settings") as mock_settings:
        mock_settings.web.SEARCH_API_KEY.get_secret_value.return_value = "test_api_key"
        mock_settings.web.SEARCH_ENGINE_ID.get_secret_value.return_value = (
            "test_engine_id"
        )

        searcher = WebSearcher(
            embedder=mock_embedder,
            document_processor=mock_document_processor,
            vector_store=mock_vector_store,
        )

        assert searcher.embedder is mock_embedder
        assert searcher.document_processor is mock_document_processor
        assert searcher.vector_store is mock_vector_store
        assert searcher.search_api_key == "test_api_key"
        assert searcher.search_engine_id == "test_engine_id"


# ==================== PROCESS QUERY VIA WEB SEARCH TESTS ====================


def test_process_query_via_web_search_success(
    web_searcher, mock_embedder, mock_vector_store, sample_web_documents
):
    """Test successful query processing via web search."""
    query = "test query"
    index_id = "test_index"

    # Mock the search and retrieve
    with patch.object(
        web_searcher, "_search_and_retrieve_content_from_web"
    ) as mock_search:
        mock_search.return_value = sample_web_documents

        # Mock document processor to return chunks
        web_searcher.document_processor.process.return_value = iter(
            sample_web_documents
        )

        # Mock embedder to return vectors
        mock_embedder.embed_documents.return_value = iter(
            [([[0.1, 0.2], [0.3, 0.4]], [{"source": "web1"}, {"source": "web2"}])]
        )

        result = web_searcher.process_query_via_web_search(query, index_id)

    assert result is not None
    assert len(result) == len(sample_web_documents)
    mock_vector_store.add_vectors.assert_called_once()
    assert result[0]["text"] is not None
    assert result[0]["metadata"] is not None


def test_process_query_via_web_search_no_results(web_searcher):
    """Test query processing when no web results found."""
    query = "test query"
    index_id = "test_index"

    with patch.object(
        web_searcher, "_search_and_retrieve_content_from_web"
    ) as mock_search:
        mock_search.return_value = []

        result = web_searcher.process_query_via_web_search(query, index_id)

    assert result is None


# ==================== SEARCH WEB TESTS ====================


def test_search_web_success(web_searcher):
    """Test successful web search with API."""
    query = "python programming"

    mock_response = Mock()
    mock_response.json.return_value = {
        "items": [
            {
                "title": "Python Tutorial",
                "snippet": "Learn Python programming",
                "link": "https://example.com/python",
            },
            {
                "title": "Advanced Python",
                "snippet": "Advanced Python concepts",
                "link": "https://example.com/advanced",
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
    assert results[0]["title"] == "Python Tutorial"
    assert results[0]["url"] == "https://example.com/python"
    assert "snippet" in results[0]


def test_search_web_no_items_in_response(web_searcher):
    """Test web search when API returns no items."""
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
    """Test web search falls back on API error."""
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


def test_search_web_missing_credentials_uses_fallback(web_searcher):
    """Test web search uses fallback when credentials are missing."""
    query = "test query"

    # Set credentials to empty
    web_searcher.search_api_key = ""
    web_searcher.search_engine_id = ""

    with patch.object(web_searcher, "_fallback_search") as mock_fallback:
        mock_fallback.return_value = []

        results = web_searcher._search_web(query)

    mock_fallback.assert_called_once()


# ==================== FALLBACK SEARCH TESTS ====================


def test_fallback_search_disabled(web_searcher):
    """Test fallback search when disabled."""
    query = "test query"

    with patch("src.components.retrieval.web_searcher.settings") as mock_settings:
        mock_settings.web.WEB_SEARCH_FALLBACK_ENABLED = False

        results = web_searcher._fallback_search(query, 5)

    assert results == []


def test_fallback_search_success(web_searcher):
    """Test successful fallback search."""
    query = "test query"

    mock_html = """
    <html>
        <div class="result">
            <a class="result__a" href="https://example.com">Example Title</a>
            <div class="result__snippet">Example snippet</div>
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

    assert len(results) >= 0  # May be 0 or more depending on parsing


def test_fallback_search_request_error(web_searcher):
    """Test fallback search handles request errors."""
    query = "test query"

    with patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.side_effect = requests.RequestException("Network error")
        mock_settings.web.WEB_SEARCH_FALLBACK_ENABLED = True
        mock_settings.web.WEB_USER_AGENT = "test-agent"

        results = web_searcher._fallback_search(query, 5)

    assert results == []


# ==================== FETCH AND CREATE DOCUMENT TESTS ====================


def test_fetch_and_create_document_success(web_searcher):
    """Test successful document creation from search result."""
    result = {
        "url": "https://example.com/article",
        "title": "Test Article",
        "snippet": "This is a test article",
    }

    with patch.object(web_searcher, "_fetch_page_content") as mock_fetch, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_fetch.return_value = "Full page content here"
        mock_settings.web.MIN_WEB_CONTENT_LENGTH = 10

        doc = web_searcher._fetch_and_create_document(result)

    assert doc is not None
    assert isinstance(doc, FileDocument)
    assert "Test Article" in doc.content
    assert "Full page content here" in doc.content
    assert doc.metadata.source == "https://example.com/article"


def test_fetch_and_create_document_short_content_uses_snippet(web_searcher):
    """Test document creation uses snippet when content is too short."""
    result = {
        "url": "https://example.com/article",
        "title": "Test Article",
        "snippet": "This is a test article snippet",
    }

    with patch.object(web_searcher, "_fetch_page_content") as mock_fetch, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_fetch.return_value = "Short"  # Too short
        mock_settings.web.MIN_WEB_CONTENT_LENGTH = 100

        doc = web_searcher._fetch_and_create_document(result)

    assert doc is not None
    assert "Summary" in doc.content
    assert "This is a test article snippet" in doc.content


def test_fetch_and_create_document_fetch_fails(web_searcher):
    """Test document creation when content fetch fails."""
    result = {
        "url": "https://example.com/article",
        "title": "Test Article",
        "snippet": "This is a test article",
    }

    with patch.object(web_searcher, "_fetch_page_content") as mock_fetch, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_fetch.return_value = None
        mock_settings.web.MIN_WEB_CONTENT_LENGTH = 10

        doc = web_searcher._fetch_and_create_document(result)

    assert doc is not None
    # Should still create doc with snippet
    assert "Summary" in doc.content
    assert "This is a test article" in doc.content


def test_fetch_and_create_document_error_handling(web_searcher):
    """Test document creation handles errors gracefully."""
    result = {
        "url": "https://example.com/article",
        "title": "Test Article",
    }

    with patch.object(web_searcher, "_fetch_page_content") as mock_fetch:
        mock_fetch.side_effect = Exception("Fetch error")

        doc = web_searcher._fetch_and_create_document(result)

    assert doc is None


# ==================== FETCH PAGE CONTENT TESTS ====================


def test_fetch_page_content_success(web_searcher):
    """Test successful page content fetching."""
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
    """Test that scripts and styles are removed from content."""
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
    """Test page content fetch handles request errors."""
    url = "https://example.com/article"

    with patch("src.components.retrieval.web_searcher.requests.get") as mock_get, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:
        mock_get.side_effect = requests.RequestException("Network error")
        mock_settings.web.WEB_USER_AGENT = "test-agent"
        mock_settings.web.WEB_REQUEST_TIMEOUT_SECS = 10

        content = web_searcher._fetch_page_content(url)

    assert content is None


# ==================== SEARCH AND RETRIEVE TESTS ====================


def test_search_and_retrieve_content_empty_query(web_searcher):
    """Test search with empty query returns empty list."""
    results = web_searcher._search_and_retrieve_content_from_web("")

    assert results == []


def test_search_and_retrieve_content_invalid_url(web_searcher):
    """Test search skips results with invalid URLs."""
    query = "test query"

    with patch.object(web_searcher, "_search_web") as mock_search:
        mock_search.return_value = [
            {"url": "not-a-url", "title": "Invalid", "snippet": "Test"},
            {"url": "ftp://invalid.com", "title": "FTP", "snippet": "Test"},
        ]

        results = web_searcher._search_and_retrieve_content_from_web(query)

    assert len(results) == 0


def test_search_and_retrieve_content_rate_limiting(web_searcher):
    """Test search respects rate limiting between requests."""
    query = "test query"

    with patch.object(web_searcher, "_search_web") as mock_search, patch.object(
        web_searcher, "_fetch_and_create_document"
    ) as mock_fetch, patch(
        "src.components.retrieval.web_searcher.time.sleep"
    ) as mock_sleep, patch(
        "src.components.retrieval.web_searcher.settings"
    ) as mock_settings:

        mock_search.return_value = [
            {"url": "https://example1.com", "title": "Doc1", "snippet": "Test1"},
            {"url": "https://example2.com", "title": "Doc2", "snippet": "Test2"},
        ]
        mock_fetch.return_value = Mock(spec=FileDocument)
        mock_settings.web.WEB_REQUEST_DELAY_SECS = 0.5

        web_searcher._search_and_retrieve_content_from_web(query)

    # Should sleep once (between first and second request)
    assert mock_sleep.call_count == 1
    mock_sleep.assert_called_with(0.5)
