"""
Unit tests for the Embedder component.
Tests core functionality and edge cases.
"""

from unittest.mock import Mock, patch

import pytest

from src.components.retrieval.embedder import Embedder
from src.errors.api_exceptions import ApiException

# ==================== INITIALIZATION ====================


def test_embedder_initialization_success():
    """Test successful embedder initialization."""
    with patch("src.components.retrieval.embedder.OpenAIEmbeddings") as mock_openai:
        mock_openai.return_value = Mock()
        embedder = Embedder()
        assert embedder.embedding_model is not None


def test_embedder_initialization_failure():
    """Test embedder initialization failure when model fails."""
    with patch("src.components.retrieval.embedder.OpenAIEmbeddings") as mock_openai:
        mock_openai.side_effect = Exception("API Error")

        with pytest.raises(ApiException) as exc_info:
            Embedder()

        assert exc_info.value.error.code == "EMBEDDER_INIT_ERROR"


# ==================== EMBED QUERY ====================


def test_embed_query_success(embedder, sample_embedding):
    """Test successful query embedding."""
    embedder.embedding_model.embed_query.return_value = sample_embedding

    result = embedder.embed_query("test query")

    assert result == sample_embedding
    embedder.embedding_model.embed_query.assert_called_once_with("test query")


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
    embedder.embedding_model.embed_query.return_value = sample_embedding

    embedder.embed_query("  test query  ")

    embedder.embedding_model.embed_query.assert_called_with("test query")


def test_embed_query_api_failure(embedder):
    """Test query embedding handles API failures gracefully."""
    embedder.embedding_model.embed_query.side_effect = Exception("API Error")

    with pytest.raises(ApiException) as exc_info:
        embedder.embed_query("test query")

    assert exc_info.value.error.code == "EMBEDDER_EMBED_QUERY_ERROR"


# ==================== EMBED DOCUMENTS ====================


def test_embed_documents_single_batch(embedder, sample_documents):
    """Test embedding documents that fit in a single batch."""
    embedder.embedding_model.embed_documents.return_value = [
        [0.1, 0.2],
        [0.3, 0.4],
        [0.5, 0.6],
    ]

    with patch("src.components.retrieval.embedder.settings") as mock_settings:
        mock_settings.vector.VECTOR_BATCH_SIZE = 10

        results = list(embedder.embed_documents(sample_documents))

    assert len(results) == 1
    assert results[0] == [
        [0.1, 0.2],
        [0.3, 0.4],
        [0.5, 0.6],
    ]
    embedder.embedding_model.embed_documents.assert_called_once_with(sample_documents)


def test_embed_documents_multiple_batches(embedder):
    """Test embedding documents across multiple batches."""
    docs = [f"Content {i}" for i in range(5)]

    embedder.embedding_model.embed_documents.side_effect = [
        [[0.1, 0.2], [0.3, 0.4]],
        [[0.5, 0.6], [0.7, 0.8]],
        [[0.9, 1.0]],
    ]

    with patch("src.components.retrieval.embedder.settings") as mock_settings:
        mock_settings.vector.VECTOR_BATCH_SIZE = 2

        results = list(embedder.embed_documents(docs))

    # Should have 3 batches: [2, 2, 1]
    assert len(results) == 3
    assert [len(batch) for batch in results] == [2, 2, 1]
    assert results[0] == [[0.1, 0.2], [0.3, 0.4]]
    assert results[1] == [[0.5, 0.6], [0.7, 0.8]]
    assert results[2] == [[0.9, 1.0]]


def test_embed_documents_api_failure(embedder, sample_documents):
    """Test document embedding handles API failures."""
    embedder.embedding_model.embed_documents.side_effect = Exception("API Error")

    with patch("src.components.retrieval.embedder.settings") as mock_settings:
        mock_settings.vector.VECTOR_BATCH_SIZE = 10

        with pytest.raises(ApiException) as exc_info:
            list(embedder.embed_documents(sample_documents))

    assert exc_info.value.error.code == "EMBEDDING_ERROR"


def test_health_check(embedder):
    """Test embedder health check returns correct status."""
    embedder.embedding_model.model = "text-embedding-3-small"

    health = embedder.health_check()

    assert health["embedder_status"] == "healthy"
    assert health["model_name"] == "text-embedding-3-small"
