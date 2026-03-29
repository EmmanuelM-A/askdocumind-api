"""
Unit tests for the QueryHandler component.
Tests query processing and response generation functionality.
"""

from unittest.mock import Mock, patch

import numpy as np
import pytest

from src.components.chatbot.query_handler import QueryHandler
from src.errors.api_exceptions import ApiException

# ==================== INITIALIZATION TESTS ====================


def test_query_handler_initialization(mock_embedder):
    """Test successful QueryHandler initialization."""
    handler = QueryHandler(embedder=mock_embedder)

    assert handler.embedder is mock_embedder
    assert handler.llm_model_name is not None


def test_query_handler_initialization_with_embedder(mock_embedder):
    """Test QueryHandler stores embedder reference correctly."""
    handler = QueryHandler(embedder=mock_embedder)

    assert handler.embedder == mock_embedder


# ==================== SEARCH FOR VECTOR TESTS ====================


def test_search_for_vector_success(
    query_handler, mock_faiss_index, sample_vector_metadata
):
    """Test successful vector search with valid inputs."""
    query = "test query"
    query_handler.embedder.embed_query.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]

    # Mock FAISS search to return indices
    mock_faiss_index.search.return_value = (
        np.array([[0.5, 0.3, 0.2]]),  # distances
        np.array([[0, 1, 2]]),  # indices
    )

    with patch("src.components.chatbot.query_handler.sanitize_query") as mock_sanitize:
        mock_sanitize.return_value = query

        results = query_handler.search_for_vector(
            query, mock_faiss_index, sample_vector_metadata
        )

    assert results is not None
    assert len(results) == 3
    assert results[0]["text"] == "Content 0"
    assert "meta" in results[0]
    query_handler.embedder.embed_query.assert_called_once_with(query)


def test_search_for_vector_missing_index(query_handler, sample_vector_metadata):
    """Test search raises error when index is None."""
    with pytest.raises(ApiException) as exc_info:
        query_handler.search_for_vector("test query", None, sample_vector_metadata)

    assert exc_info.value.error.code == "MISSING_FAISS_INDEX"


def test_search_for_vector_invalid_metadata(query_handler, mock_faiss_index):
    """Test search raises error when metadata is invalid."""
    with pytest.raises(ApiException) as exc_info:
        query_handler.search_for_vector("test query", mock_faiss_index, None)

    assert exc_info.value.error.code == "INVALID_METADATA"


def test_search_for_vector_metadata_not_dict(query_handler, mock_faiss_index):
    """Test search raises error when metadata is not a dictionary."""
    with pytest.raises(ApiException) as exc_info:
        query_handler.search_for_vector("test query", mock_faiss_index, "invalid")

    assert exc_info.value.error.code == "INVALID_METADATA"


def test_search_for_vector_no_indices_found(
    query_handler, mock_faiss_index, sample_vector_metadata
):
    """Test search returns None when no indices are found."""
    query_handler.embedder.embed_query.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]

    # Return empty indices
    mock_faiss_index.search.return_value = (
        np.array([[]]),
        np.array([[]]),
    )

    with patch("src.components.chatbot.query_handler.sanitize_query") as mock_sanitize:
        mock_sanitize.return_value = "test query"

        results = query_handler.search_for_vector(
            "test query", mock_faiss_index, sample_vector_metadata
        )

    assert results is None


def test_search_for_vector_missing_text_in_metadata(query_handler, mock_faiss_index):
    """Test search skips entries with missing 'text' field."""
    query_handler.embedder.embed_query.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]

    # Metadata with missing 'text' field
    metadata = {
        0: {"meta": {"source": "doc1.txt"}},  # Missing 'text'
        1: {"text": "Content 1", "meta": {"source": "doc2.txt"}},
    }

    mock_faiss_index.search.return_value = (
        np.array([[0.5, 0.3]]),
        np.array([[0, 1]]),
    )

    with patch("src.components.chatbot.query_handler.sanitize_query") as mock_sanitize:
        mock_sanitize.return_value = "test query"

        results = query_handler.search_for_vector(
            "test query", mock_faiss_index, metadata
        )

    # Should only return the valid entry
    assert len(results) == 1
    assert results[0]["text"] == "Content 1"


def test_search_for_vector_missing_meta_in_metadata(query_handler, mock_faiss_index):
    """Test search skips entries with missing 'meta' field."""
    query_handler.embedder.embed_query.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]

    # Metadata with missing 'meta' field
    metadata = {
        0: {"text": "Content 0"},  # Missing 'meta'
        1: {"text": "Content 1", "meta": {"source": "doc2.txt"}},
    }

    mock_faiss_index.search.return_value = (
        np.array([[0.5, 0.3]]),
        np.array([[0, 1]]),
    )

    with patch("src.components.chatbot.query_handler.sanitize_query") as mock_sanitize:
        mock_sanitize.return_value = "test query"

        results = query_handler.search_for_vector(
            "test query", mock_faiss_index, metadata
        )

    # Should only return the valid entry
    assert len(results) == 1
    assert results[0]["text"] == "Content 1"


def test_search_for_vector_sanitizes_query(
    query_handler, mock_faiss_index, sample_vector_metadata
):
    """Test that search sanitizes the query before processing."""
    query_handler.embedder.embed_query.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]

    mock_faiss_index.search.return_value = (
        np.array([[0.5]]),
        np.array([[0]]),
    )

    with patch("src.components.chatbot.query_handler.sanitize_query") as mock_sanitize:
        mock_sanitize.return_value = "sanitized query"

        query_handler.search_for_vector(
            "<script>malicious</script>", mock_faiss_index, sample_vector_metadata
        )

        mock_sanitize.assert_called_once()


# ==================== GENERATE RESPONSES TESTS ====================


def test_generate_responses_success(query_handler, sample_retrieved_chunks):
    """Test successful response generation."""
    query = "What is the test content?"

    with patch("src.components.chatbot.query_handler.ChatOpenAI"), patch(
        "src.components.chatbot.query_handler.create_prompt_template"
    ) as mock_prompt, patch(
        "src.components.chatbot.query_handler.StrOutputParser"
    ) as mock_parser:

        # Mock the final chain (after all | operations)
        mock_final_chain = Mock()
        mock_final_chain.invoke.return_value = (
            "This is the answer based on the context."
        )

        # Mock intermediate chain (prompt_template | llm)
        mock_intermediate_chain = Mock()
        mock_intermediate_chain.__or__ = Mock(return_value=mock_final_chain)

        # Mock prompt template
        mock_template = Mock()
        mock_template.__or__ = Mock(return_value=mock_intermediate_chain)
        mock_prompt.return_value = mock_template

        # Mock the parser instance
        mock_parser.return_value = Mock()

        result = query_handler.generate_responses(query, sample_retrieved_chunks)

    assert result is not None
    assert "answer" in result
    assert "sources" in result
    assert result["answer"] == "This is the answer based on the context."
    assert len(result["sources"]) > 0


def test_generate_responses_need_web_search(query_handler, sample_retrieved_chunks):
    """Test response generation returns None when web search is needed."""
    query = "What is the weather today?"

    with patch("src.components.chatbot.query_handler.ChatOpenAI"), patch(
        "src.components.chatbot.query_handler.create_prompt_template"
    ) as mock_prompt, patch(
        "src.components.chatbot.query_handler.StrOutputParser"
    ) as mock_parser:

        # Mock the final chain to return NEED_WEB_SEARCH
        mock_final_chain = Mock()
        mock_final_chain.invoke.return_value = "NEED_WEB_SEARCH"

        mock_intermediate_chain = Mock()
        mock_intermediate_chain.__or__ = Mock(return_value=mock_final_chain)

        mock_template = Mock()
        mock_template.__or__ = Mock(return_value=mock_intermediate_chain)
        mock_prompt.return_value = mock_template

        mock_parser.return_value = Mock()

        result = query_handler.generate_responses(query, sample_retrieved_chunks)

    assert result is None


def test_generate_responses_extracts_sources(query_handler):
    """Test that sources are correctly extracted from chunks."""
    query = "test query"
    chunks = [
        {"text": "Content 1", "meta": {"source": "doc1.txt"}},
        {"text": "Content 2", "meta": {"source": "doc2.txt"}},
        {"text": "Content 3", "meta": {"source": "doc1.txt"}},  # Duplicate
    ]

    with patch("src.components.chatbot.query_handler.ChatOpenAI"), patch(
        "src.components.chatbot.query_handler.create_prompt_template"
    ) as mock_prompt, patch(
        "src.components.chatbot.query_handler.StrOutputParser"
    ) as mock_parser:

        mock_final_chain = Mock()
        mock_final_chain.invoke.return_value = "Answer"

        mock_intermediate_chain = Mock()
        mock_intermediate_chain.__or__ = Mock(return_value=mock_final_chain)

        mock_template = Mock()
        mock_template.__or__ = Mock(return_value=mock_intermediate_chain)
        mock_prompt.return_value = mock_template

        mock_parser.return_value = Mock()

        result = query_handler.generate_responses(query, chunks)

    assert result is not None
    assert len(result["sources"]) == 2  # Duplicates removed
    assert "doc1.txt" in result["sources"]
    assert "doc2.txt" in result["sources"]


def test_generate_responses_handles_dict_metadata(query_handler):
    """Test response generation handles dictionary metadata."""
    query = "test query"
    chunks = [
        {"text": "Content", "meta": {"source": "doc.txt", "extra": "data"}},
    ]

    with patch("src.components.chatbot.query_handler.ChatOpenAI"), patch(
        "src.components.chatbot.query_handler.create_prompt_template"
    ) as mock_prompt, patch(
        "src.components.chatbot.query_handler.StrOutputParser"
    ) as mock_parser:

        mock_final_chain = Mock()
        mock_final_chain.invoke.return_value = "Answer"

        mock_intermediate_chain = Mock()
        mock_intermediate_chain.__or__ = Mock(return_value=mock_final_chain)

        mock_template = Mock()
        mock_template.__or__ = Mock(return_value=mock_intermediate_chain)
        mock_prompt.return_value = mock_template

        mock_parser.return_value = Mock()

        result = query_handler.generate_responses(query, chunks)

    assert "doc.txt" in result["sources"]


def test_generate_responses_handles_object_metadata(query_handler):
    """Test response generation handles object metadata with source attribute."""
    query = "test query"

    # Create a mock metadata object
    mock_metadata = Mock()
    mock_metadata.source = "object_source.txt"

    chunks = [
        {"text": "Content", "meta": mock_metadata},
    ]

    with patch("src.components.chatbot.query_handler.ChatOpenAI"), patch(
        "src.components.chatbot.query_handler.create_prompt_template"
    ) as mock_prompt, patch(
        "src.components.chatbot.query_handler.StrOutputParser"
    ) as mock_parser:

        mock_final_chain = Mock()
        mock_final_chain.invoke.return_value = "Answer"

        mock_intermediate_chain = Mock()
        mock_intermediate_chain.__or__ = Mock(return_value=mock_final_chain)

        mock_template = Mock()
        mock_template.__or__ = Mock(return_value=mock_intermediate_chain)
        mock_prompt.return_value = mock_template

        mock_parser.return_value = Mock()

        result = query_handler.generate_responses(query, chunks)

    assert "object_source.txt" in result["sources"]


def test_generate_responses_handles_missing_sources(query_handler):
    """Test response generation handles chunks without sources gracefully."""
    query = "test query"
    chunks = [
        {"text": "Content 1", "meta": {}},  # No source
        {"text": "Content 2", "meta": {"source": "doc.txt"}},
    ]

    with patch("src.components.chatbot.query_handler.ChatOpenAI"), patch(
        "src.components.chatbot.query_handler.create_prompt_template"
    ) as mock_prompt, patch(
        "src.components.chatbot.query_handler.StrOutputParser"
    ) as mock_parser:

        mock_final_chain = Mock()
        mock_final_chain.invoke.return_value = "Answer"

        mock_intermediate_chain = Mock()
        mock_intermediate_chain.__or__ = Mock(return_value=mock_final_chain)

        mock_template = Mock()
        mock_template.__or__ = Mock(return_value=mock_intermediate_chain)
        mock_prompt.return_value = mock_template

        mock_parser.return_value = Mock()

        result = query_handler.generate_responses(query, chunks)

    assert len(result["sources"]) == 1
    assert "doc.txt" in result["sources"]


def test_generate_responses_context_formatting(query_handler, sample_retrieved_chunks):
    """Test that context is properly formatted for the LLM."""
    query = "test query"

    with patch("src.components.chatbot.query_handler.ChatOpenAI"), patch(
        "src.components.chatbot.query_handler.create_prompt_template"
    ) as mock_prompt, patch(
        "src.components.chatbot.query_handler.StrOutputParser"
    ) as mock_parser:

        mock_final_chain = Mock()
        mock_final_chain.invoke.return_value = "Answer"

        mock_intermediate_chain = Mock()
        mock_intermediate_chain.__or__ = Mock(return_value=mock_final_chain)

        mock_template = Mock()
        mock_template.__or__ = Mock(return_value=mock_intermediate_chain)
        mock_prompt.return_value = mock_template

        mock_parser.return_value = Mock()

        query_handler.generate_responses(query, sample_retrieved_chunks)

        # Verify the chain was invoked with properly formatted context
        call_args = mock_final_chain.invoke.call_args[0][0]
        assert "context" in call_args
        assert "query" in call_args
        assert "\n\n" in call_args["context"]  # Check for double newline separator
