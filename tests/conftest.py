"""
Global test fixtures and configurations for all tests
"""

import io
import sys
import uuid
from unittest.mock import Mock, patch

from src.database.connection import DatabaseConnection
from src.database.models import User, ChatSession

# Mock problematic imports BEFORE any other imports that might use them
sys.modules["docx"] = Mock()
sys.modules["fitz"] = Mock()

import pytest
from fastapi import UploadFile

from src.components.retrieval.embedder import Embedder

from src.components.ingestion.document import FileDocumentMetadata, FileDocument
from src.components.ingestion.document_processor import DocumentProcessor
from src.api.services.caching.cache_factory import CacheFactory
from src.components.retrieval.faiss_store import FaissVectorStore

# ============================ CACHE FIXTURES ============================


@pytest.fixture
def cache():
    """
    Provides a fresh cache instance per test using a unique namespace.
    """

    namespace = f"test:{uuid.uuid4().hex}"
    c = CacheFactory.get_cache(namespace=namespace)
    yield c
    c.clear()
    c.close()


# ========================= COMMON DATABASE FIXTURES =========================


@pytest.fixture
async def db_connection():
    """Provide a database connection for tests."""
    conn = DatabaseConnection()
    await conn.connect()
    yield conn
    await conn.disconnect()


@pytest.fixture
async def test_user(db_connection):
    """Create a test user for document ownership."""
    user = User()
    async with db_connection.get_session() as session:
        session.add(user)
        await session.commit()
    try:
        yield user
    finally:
        from sqlalchemy import delete

        async with db_connection.get_session() as session:
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()


@pytest.fixture
async def test_chat_session(db_connection, test_user):
    """Create a test chat session."""
    chat_session = ChatSession(user_id=test_user.id)
    async with db_connection.get_session() as db_session:
        db_session.add(chat_session)
        await db_session.commit()
    try:
        yield chat_session
    finally:
        from sqlalchemy import delete

        async with db_connection.get_session() as db_session:
            await db_session.execute(
                delete(ChatSession).where(ChatSession.id == chat_session.id)
            )
            await db_session.commit()


# ====================== DOCUMENT PROCESSOR FIXTURES ======================


@pytest.fixture
def processor():
    """Provides a fresh DocumentProcessor instance for each test."""
    return DocumentProcessor()


@pytest.fixture
def mock_upload_file():
    """Creates a mock UploadFile for testing."""

    def _create_upload(filename: str, content: str):
        file_obj = io.BytesIO(content.encode("utf-8"))
        upload = UploadFile(filename=filename, file=file_obj)
        return upload

    return _create_upload


@pytest.fixture
def mock_document():
    """Creates a mock FileDocument for testing."""

    def _create_doc(content: str, filename: str = "test.txt"):
        metadata = FileDocumentMetadata(filename=filename, file_extension=".txt")
        return FileDocument(content=content, metadata=metadata)

    return _create_doc


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
def sample_documents():
    """Creates a list of sample documents for testing."""
    docs = []
    for i in range(3):
        metadata = FileDocumentMetadata(
            filename=f"doc_{i}.txt", file_extension=".txt", source=f"test_source_{i}"
        )
        docs.append(FileDocument(content=f"Test content {i}", metadata=metadata))
    return docs


@pytest.fixture
def sample_embedding():
    """Returns a sample embedding vector."""
    return [0.1, 0.2, 0.3, 0.4, 0.5]


# ================== VECTOR STORE FIXTURES ==================


@pytest.fixture
def vector_store(tmp_path):
    """Provides a fresh FaissVectorStore instance with temporary directories."""

    with patch("src.components.retrieval.faiss_store.settings") as mock_settings:
        # Use temporary directories for testing
        mock_settings.vector.DEV_VECTOR_STORE = str(tmp_path / "indexes")
        mock_settings.vector.DEV_METADATA_STORE = str(tmp_path / "metadata")
        mock_settings.vector.MAX_VECTORS_IN_MEMORY = 10000
        mock_settings.vector.VECTOR_BATCH_SIZE = 100

        store = FaissVectorStore()

        yield store

        # Cleanup - delete all created indexes
        try:
            import os

            if os.path.exists(store.index_dir):
                for file in os.listdir(store.index_dir):
                    os.remove(os.path.join(store.index_dir, file))
            if os.path.exists(store.metadata_dir):
                for file in os.listdir(store.metadata_dir):
                    os.remove(os.path.join(store.metadata_dir, file))
        except Exception:
            pass


@pytest.fixture
def sample_index_id(vector_store):
    """Creates a sample empty index and returns its ID."""
    index_id = vector_store.create_vector_index()
    return index_id


@pytest.fixture
def multiple_indexes(vector_store):
    """Creates multiple empty indexes and returns their IDs."""
    index_ids = []
    for _ in range(3):
        index_id = vector_store.create_vector_index()
        index_ids.append(index_id)
    return index_ids


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
        {"filename": "doc1.txt", "source": "upload", "chunk_index": 0},
        {"filename": "doc2.txt", "source": "upload", "chunk_index": 0},
        {"filename": "doc3.txt", "source": "upload", "chunk_index": 0},
    ]


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
    # Mock PDF binary content
    return mock_upload_file_factory("test.pdf", b"%PDF-1.4 mock content", binary=True)


@pytest.fixture
def docx_upload_file(mock_upload_file_factory):
    """Creates a mock DOCX UploadFile."""
    # Mock DOCX binary content
    return mock_upload_file_factory("test.docx", b"PK mock docx", binary=True)


# ================== QUERY HANDLER FIXTURES ==================


@pytest.fixture
def mock_embedder():
    """Creates a mock Embedder instance."""
    mock_emb = Mock()
    mock_emb.embed_query.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]
    return mock_emb


@pytest.fixture
def query_handler(mock_embedder):
    """Provides a QueryHandler instance with mocked embedder."""
    from src.components.chatbot.query_handler import QueryHandler

    handler = QueryHandler(embedder=mock_embedder)
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
    """Creates a mock DocumentProcessor instance."""
    mock_proc = Mock()
    mock_proc.process.return_value = iter([])
    return mock_proc


@pytest.fixture
def mock_vector_store():
    """Creates a mock VectorStore instance."""
    mock_store = Mock()
    return mock_store


@pytest.fixture
def web_searcher(mock_embedder, mock_document_processor, mock_vector_store):
    """Provides a WebSearcher instance with mocked dependencies."""
    from src.components.retrieval.web_searcher import WebSearcher

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

        yield searcher


@pytest.fixture
def sample_web_documents():
    """Creates sample web documents for testing."""
    from src.components.ingestion.document import FileDocument, FileDocumentMetadata

    docs = []
    for i in range(2):
        metadata = FileDocumentMetadata(
            filename=f"web_doc_{i}",
            file_extension=".html",
            source=f"https://example.com/page{i}",
        )
        docs.append(
            FileDocument(
                content=f"Web content {i} with lots of text", metadata=metadata
            )
        )
    return docs
