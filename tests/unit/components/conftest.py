"""
Fixtures for component tests (extractors, document processor, etc.)
"""

import io
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import UploadFile

from src.components.ingestion.document_processor import UploadedDocumentProcessor
from src.components.retrieval.embedder import Embedder


# ====================== DOCUMENT PROCESSOR FIXTURES ======================


@pytest.fixture
def processor():
    """Provides a fresh UploadedDocumentProcessor instance for each test."""
    return UploadedDocumentProcessor()


@pytest.fixture
def mock_upload_file():
    """Creates a mock UploadFile for testing."""

    def _create_upload(filename: str, content: str):
        file_obj = io.BytesIO(content.encode("utf-8"))
        upload = UploadFile(filename=filename, file=file_obj)
        return upload

    return _create_upload


# ================== TEXT EXTRACTOR FIXTURES ==================


@pytest.fixture
def mock_upload_file_factory():
    """Factory for creating mock UploadFile instances."""

    def _create_upload(filename: str, content, binary=False):
        if binary:
            file_obj = io.BytesIO(
                content if isinstance(content, bytes) else content.encode()
            )
        else:
            file_obj = io.BytesIO(
                content.encode("utf-8") if isinstance(content, str) else content
            )

        upload = UploadFile(filename=filename, file=file_obj)
        return upload

    return _create_upload


@pytest.fixture
def txt_upload_file(mock_upload_file_factory):
    """Creates a mock TXT UploadFile."""
    return mock_upload_file_factory("test.txt", "This is test content")


@pytest.fixture
def md_upload_file(mock_upload_file_factory):
    """Creates a mock Markdown UploadFile."""
    content = "# Test Heading\n\nThis is markdown content"
    return mock_upload_file_factory("test.md", content)


@pytest.fixture
def pdf_upload_file(mock_upload_file_factory):
    """Creates a mock PDF UploadFile."""
    return mock_upload_file_factory("test.pdf", b"%PDF-1.4 mock content", binary=True)


@pytest.fixture
def docx_upload_file(mock_upload_file_factory):
    """Creates a mock DOCX UploadFile."""
    return mock_upload_file_factory("test.docx", b"PK mock docx", binary=True)

# ================== EMBEDDER FIXTURES ==================


@pytest.fixture
def embedder():
    """Provides a fresh Embedder instance for each test with mocked dependencies."""
    with patch(
        "src.components.retrieval.embedder.OpenAIEmbeddings"
    ) as mock_openai, patch(
        "src.components.retrieval.embedder.CacheFactory"
    ) as mock_cache_factory:

        # Mock the embedding model
        mock_model = Mock()
        mock_model.model = "text-embedding-3-small"
        mock_openai.return_value = mock_model

        # Mock cache instances
        mock_doc_cache = Mock()
        mock_query_cache = Mock()

        # Set up cache factory to return mocked caches
        def get_cache_side_effect(namespace):
            if "documents" in namespace.lower():
                return mock_doc_cache

            if "queries" in namespace.lower():
                return mock_query_cache

            return Mock()

        mock_cache_factory.get_cache.side_effect = get_cache_side_effect

        # Create embedder instance
        emb = Embedder()

        yield emb

        # Cleanup
        emb.clear_caches()


@pytest.fixture
def sample_embedding():
    """Returns a sample embedding vector."""
    return [0.1, 0.2, 0.3, 0.4, 0.5]


@pytest.fixture
def sample_documents():
    """Returns sample text documents for embedder tests."""
    return [
        "Document one content.",
        "Document two content.",
        "Document three content.",
    ]

# ================== VECTOR STORE FIXTURES ==================


@pytest.fixture
def sample_vectors():
    """Returns sample vectors for testing."""
    return [
        [0.1, 0.2, 0.3, 0.4, 0.5],
        [0.2, 0.3, 0.4, 0.5, 0.6],
        [0.3, 0.4, 0.5, 0.6, 0.7],
    ]


@pytest.fixture
def sample_metadata():
    """Returns sample metadata for testing."""
    return [
        {"filename": "doc1.txt", "source": "upload"},
        {"filename": "doc2.txt", "source": "upload"},
        {"filename": "doc3.txt", "source": "upload"},
    ]


# ================== QUERY HANDLER FIXTURES ==================


@pytest.fixture
def mock_embedder():
    """Creates a mock Embedder instance."""
    mock_emb = Mock()
    mock_emb.embed_query.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]
    return mock_emb


@pytest.fixture
def mock_document_chunk_repo():
    """Creates a mock DocumentChunk repository for query handler tests."""
    mock_repo = Mock()
    mock_repo.search_similar = AsyncMock(return_value=[])
    mock_repo.get_filenames_for_chunks = AsyncMock(return_value=[])
    return mock_repo


@pytest.fixture
def query_handler(mock_embedder, mock_document_chunk_repo):
    """Provides a QueryHandler instance with mocked embedder."""
    from src.components.chatbot.query_handler import QueryHandler

    with patch("src.components.chatbot.query_handler.ChatOpenAI") as mock_llm, patch(
        "src.components.chatbot.query_handler.create_prompt_template"
    ) as mock_prompt:
        mock_llm.return_value = MagicMock()
        mock_prompt.return_value = MagicMock()

        handler = QueryHandler(
            embedder=mock_embedder,
            document_chunk_repo=mock_document_chunk_repo,
        )
        return handler


@pytest.fixture
def mock_faiss_index():
    """Creates a mock FAISS index."""
    import numpy as np

    mock_index = Mock()
    mock_index.search.return_value = (
        np.array([[0.5, 0.3, 0.2]]),  # distances
        np.array([[0, 1, 2]]),  # indices
    )
    return mock_index


@pytest.fixture
def sample_vector_metadata():
    """Creates sample vector search metadata."""
    return {
        0: {"text": "Content 0", "meta": {"source": "doc0.txt"}},
        1: {"text": "Content 1", "meta": {"source": "doc1.txt"}},
        2: {"text": "Content 2", "meta": {"source": "doc2.txt"}},
    }


@pytest.fixture
def sample_retrieved_chunks():
    """Creates sample retrieved chunks for response generation."""
    return [
        {"text": "First chunk content", "meta": {"source": "doc1.txt"}},
        {"text": "Second chunk content", "meta": {"source": "doc2.txt"}},
        {"text": "Third chunk content", "meta": {"source": "doc1.txt"}},
    ]


# ================== WEB SEARCHER FIXTURES ==================


@pytest.fixture
def mock_document_processor():
    """Creates a mock UploadedDocumentProcessor instance."""
    mock_proc = Mock()
    mock_proc.process.return_value = iter([])
    return mock_proc


@pytest.fixture
def mock_vector_store():
    """Creates a mock VectorStore instance."""
    mock_store = Mock()
    return mock_store


@pytest.fixture
def mock_vector_processor():
    """Creates a mock VectorProcessor instance."""
    mock_processor = Mock()
    mock_processor.process_and_save_vectors_from_web = AsyncMock(return_value=0)
    return mock_processor


@pytest.fixture
def web_searcher(mock_embedder, mock_vector_processor):
    """Provides a WebSearcher instance with mocked dependencies."""
    from src.components.retrieval.web_searcher import WebSearcher

    with patch("src.components.retrieval.web_searcher.settings") as mock_settings:
        mock_settings.web.SEARCH_API_KEY.get_secret_value.return_value = "test_api_key"
        mock_settings.web.SEARCH_ENGINE_ID.get_secret_value.return_value = (
            "test_engine_id"
        )

        searcher = WebSearcher(
            embedder=mock_embedder,
            vector_processor=mock_vector_processor,
        )

        yield searcher