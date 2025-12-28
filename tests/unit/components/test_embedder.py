"""
Unit tests for the Embedder component.
Tests core functionality and edge cases.
"""

from unittest.mock import Mock, patch

import pytest

from src.components.retrieval.embedder import Embedder
from src.components.ingestion.document import FileDocument, FileDocumentMetadata
from src.errors.api_exceptions import ApiException


# ==================== INITIALIZATION ====================


def test_embedder_initialization_success():
    """Test successful embedder initialization."""
    with patch(
        "src.components.retrieval.embedder.OpenAIEmbeddings"
    ) as mock_openai, patch("src.components.retrieval.embedder.CacheFactory"):

        mock_openai.return_value = Mock()
        embedder = Embedder()

        assert embedder.embedding_model is not None
        assert embedder.documents_cache is not None
        assert embedder.queries_cache is not None


def test_embedder_initialization_failure():
    """Test embedder initialization failure when model fails."""
    with patch(
        "src.components.retrieval.embedder.OpenAIEmbeddings"
    ) as mock_openai, patch("src.components.retrieval.embedder.CacheFactory"):

        mock_openai.side_effect = Exception("API Error")

        with pytest.raises(ApiException) as exc_info:
            Embedder()

        assert exc_info.value.error.code == "EMBEDDER_INIT_ERROR"


# ==================== EMBED QUERY ====================


def test_embed_query_success(embedder, sample_embedding):
    """Test successful query embedding without cache."""
    embedder.queries_cache.get.return_value = None
    embedder.embedding_model.embed_query.return_value = sample_embedding

    result = embedder.embed_query("test query")

    assert result == sample_embedding
    embedder.embedding_model.embed_query.assert_called_once_with("test query")
    embedder.queries_cache.set.assert_called_once()


def test_embed_query_with_caching(embedder, sample_embedding):
    """Test query embedding uses cache on subsequent calls."""
    # First call - cache miss, then cache hit
    embedder.queries_cache.get.side_effect = [None, sample_embedding]
    embedder.embedding_model.embed_query.return_value = sample_embedding

    # First call - should hit the model
    result1 = embedder.embed_query("cached query")
    # Second call - should use cache
    result2 = embedder.embed_query("cached query")

    assert result1 == sample_embedding
    assert result2 == sample_embedding
    # Model should only be called once
    embedder.embedding_model.embed_query.assert_called_once()


def test_embed_query_empty_string(embedder):
    """Test embedding empty query string raises error."""
    with pytest.raises(ApiException) as exc_info:
        embedder.embed_query("")

    assert exc_info.value.error.code == "NO_QUERY_PROVIDED"


def test_embed_query_whitespace_only(embedder):
    """Test embedding whitespace-only query raises error."""
    with pytest.raises(ApiException) as exc_info:
        embedder.embed_query("   \n\t  ")

    assert exc_info.value.error.code == "NO_QUERY_PROVIDED"


def test_embed_query_strips_whitespace(embedder, sample_embedding):
    """Test query embedding strips leading/trailing whitespace."""
    embedder.queries_cache.get.return_value = None
    embedder.embedding_model.embed_query.return_value = sample_embedding

    embedder.embed_query("  test query  ")

    embedder.embedding_model.embed_query.assert_called_with("test query")


def test_embed_query_api_failure(embedder):
    """Test query embedding handles API failures gracefully."""
    embedder.queries_cache.get.return_value = None
    embedder.embedding_model.embed_query.side_effect = Exception("API Error")

    with pytest.raises(ApiException) as exc_info:
        embedder.embed_query("test query")

    assert exc_info.value.error.code == "EMBEDDER_EMBED_QUERY_ERROR"


# ==================== EMBED DOCUMENTS ====================


def test_embed_documents_single_batch(embedder, sample_documents):
    """Test embedding documents that fit in a single batch."""
    # All cache misses
    embedder.documents_cache.get.return_value = None
    embedder.embedding_model.embed_documents.return_value = [
        [0.1, 0.2],
        [0.3, 0.4],
        [0.5, 0.6],
    ]

    with patch("src.components.retrieval.embedder.settings") as mock_settings:
        mock_settings.vector.VECTOR_BATCH_SIZE = 10

        results = list(embedder.embed_documents(sample_documents))

    assert len(results) == 1
    vectors, metadata = results[0]
    assert len(vectors) == 3
    assert len(metadata) == 3


def test_embed_documents_multiple_batches(embedder):
    """Test embedding documents across multiple batches."""
    # Create 5 documents
    docs = []
    for i in range(5):
        metadata = FileDocumentMetadata(filename=f"doc_{i}.txt", file_extension=".txt")
        docs.append(FileDocument(content=f"Content {i}", metadata=metadata))

    embedder.documents_cache.get.return_value = None
    embedder.embedding_model.embed_documents.return_value = [[0.1, 0.2], [0.3, 0.4]]

    with patch("src.components.retrieval.embedder.settings") as mock_settings:
        mock_settings.vector.VECTOR_BATCH_SIZE = 2

        results = list(embedder.embed_documents(docs))

    # Should have 3 batches: [2, 2, 1]
    assert len(results) == 3


def test_embed_documents_with_cache_hit(embedder):
    """Test document embedding uses cache for previously seen content."""
    doc = FileDocument(
        content="cached content",
        metadata=FileDocumentMetadata(filename="test.txt", file_extension=".txt"),
    )

    # First call - cache miss, second call - cache hit
    cached_embedding = [0.1, 0.2, 0.3]
    embedder.documents_cache.get.side_effect = [None, cached_embedding]
    embedder.embedding_model.embed_documents.return_value = [cached_embedding]

    with patch("src.components.retrieval.embedder.settings") as mock_settings:
        mock_settings.vector.VECTOR_BATCH_SIZE = 10

        # First embedding
        list(embedder.embed_documents([doc]))
        # Second embedding - should use cache
        results = list(embedder.embed_documents([doc]))

    # Verify cached result used
    vectors, _ = results[0]
    assert vectors[0] == cached_embedding


def test_embed_documents_api_failure(embedder, sample_documents):
    """Test document embedding handles API failures."""
    embedder.documents_cache.get.return_value = None
    embedder.embedding_model.embed_documents.side_effect = Exception("API Error")

    with patch("src.components.retrieval.embedder.settings") as mock_settings:
        mock_settings.vector.VECTOR_BATCH_SIZE = 10

        with pytest.raises(ApiException) as exc_info:
            list(embedder.embed_documents(sample_documents))

    assert exc_info.value.error.code == "EMBEDDING_ERROR"


# ==================== CACHE MANAGEMENT ====================


def test_clear_caches(embedder):
    """Test clearing embedder caches."""
    embedder.clear_caches()

    embedder.documents_cache.clear.assert_called_once()
    embedder.queries_cache.clear.assert_called_once()


def test_health_check(embedder):
    """Test embedder health check returns correct status."""
    embedder.embedding_model.model = "text-embedding-3-small"

    health = embedder.health_check()

    assert health["embedder_status"] == "healthy"
    assert health["model_name"] == "text-embedding-3-small"
