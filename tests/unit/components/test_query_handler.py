"""
Unit tests for the QueryHandler component.
Tests query processing and response generation functionality.
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from src.components.chatbot.query_handler import QueryHandler
from src.errors.api_exceptions import ApiException

# ==================== INITIALIZATION TESTS ====================


def test_query_handler_initialization(mock_embedder, mock_document_chunk_repo):
    """Test successful QueryHandler initialization."""
    with patch("src.components.chatbot.query_handler.ChatOpenAI") as mock_llm, patch(
        "src.components.chatbot.query_handler.create_prompt_template"
    ) as mock_prompt:
        mock_llm.return_value = Mock()
        mock_prompt.return_value = Mock()

        handler = QueryHandler(
            embedder=mock_embedder,
            document_chunk_repo=mock_document_chunk_repo,
        )

    assert handler.embedder is mock_embedder
    assert handler.document_chunk_repo is mock_document_chunk_repo
    assert handler._llm is not None
    assert handler._prompt_template is not None


@pytest.mark.asyncio
async def test_search_for_vector_success(query_handler):
    """Test successful vector search with valid inputs."""
    chat_session_id = uuid4()
    chunks = [Mock(chunk_text="Chunk 1"), Mock(chunk_text="Chunk 2")]

    query_handler.document_chunk_repo.search_similar = AsyncMock(return_value=chunks)
    query_handler.document_chunk_repo.get_filenames_for_chunks = AsyncMock(
        return_value=["doc1.txt", "doc2.txt"]
    )

    with patch(
        "src.components.chatbot.query_handler.validate_and_sanitize_query",
        return_value="sanitized query",
    ) as mock_validate, patch(
        "src.components.chatbot.query_handler.settings"
    ) as mock_settings:
        mock_settings.vector.RETRIEVAL_TOP_K = 3
        mock_settings.vector.SIMILARITY_THRESHOLD = 0.4

        result = await query_handler.search_for_vector("  test query  ", chat_session_id)

    assert result == (chunks, ["doc1.txt", "doc2.txt"])
    mock_validate.assert_called_once()
    query_handler.embedder.embed_query.assert_called_once_with("sanitized query")
    query_handler.document_chunk_repo.search_similar.assert_awaited_once_with(
        chat_session_id=chat_session_id,
        vector=[0.1, 0.2, 0.3, 0.4, 0.5],
        top_k=3,
        threshold=0.4,
    )
    query_handler.document_chunk_repo.get_filenames_for_chunks.assert_awaited_once_with(
        chunks=chunks,
        chat_session_id=chat_session_id,
    )


# ==================== SEARCH FOR VECTOR TESTS ====================


@pytest.mark.asyncio
async def test_search_for_vector_empty_query_raises_error(query_handler):
    """Test empty queries are rejected by validation."""
    with pytest.raises(ApiException) as exc_info:
        await query_handler.search_for_vector("   ", uuid4())

    assert exc_info.value.error.code == "EMPTY_QUERY"


@pytest.mark.asyncio
async def test_search_for_vector_no_results_returns_none(query_handler):
    """Test search returns None when no chunks are found."""
    chat_session_id = uuid4()

    query_handler.document_chunk_repo.search_similar = AsyncMock(return_value=[])
    query_handler.document_chunk_repo.get_filenames_for_chunks = AsyncMock(
        return_value=[]
    )

    with patch(
        "src.components.chatbot.query_handler.validate_and_sanitize_query",
        return_value="sanitized query",
    ), patch(
        "src.components.chatbot.query_handler.settings"
    ) as mock_settings:
        mock_settings.vector.RETRIEVAL_TOP_K = 3
        mock_settings.vector.SIMILARITY_THRESHOLD = 0.7

        result = await query_handler.search_for_vector("test query", chat_session_id)

    assert result == ([], [])
    query_handler.document_chunk_repo.search_similar.assert_awaited_once()
    query_handler.document_chunk_repo.get_filenames_for_chunks.assert_awaited_once()


# ==================== GENERATE RESPONSES TESTS ====================


def test_generate_responses_success(query_handler):
    """Test successful response generation."""
    query = "What is the test content?"
    chunks = [Mock(chunk_text="First chunk content"), Mock(chunk_text="Second chunk content")]

    mock_final_chain = Mock()
    mock_final_chain.invoke.return_value = "This is the answer based on the context."

    query_handler._prompt_template.__or__.return_value = query_handler._llm
    query_handler._llm.__or__.return_value = mock_final_chain

    with patch(
        "src.components.chatbot.query_handler.StrOutputParser",
        return_value=Mock(),
    ):
        result = query_handler.generate_responses(query, chunks)

    assert result == "This is the answer based on the context."
    call_args = mock_final_chain.invoke.call_args[0][0]
    assert call_args["query"] == query
    assert call_args["context"] == "First chunk content\n\nSecond chunk content"


def test_generate_responses_need_web_search(query_handler):
    """Test response generation returns None when web search is needed."""
    query = "What is the weather today?"
    chunks = [Mock(chunk_text="Context chunk")]

    mock_final_chain = Mock()
    mock_final_chain.invoke.return_value = "NEED_WEB_SEARCH"

    query_handler._prompt_template.__or__.return_value = query_handler._llm
    query_handler._llm.__or__.return_value = mock_final_chain

    with patch(
        "src.components.chatbot.query_handler.StrOutputParser",
        return_value=Mock(),
    ):
        result = query_handler.generate_responses(query, chunks)

    assert result == "NEED_WEB_SEARCH"


def test_generate_responses_need_web_search_overridden_for_web(query_handler):
    """Test NEED_WEB_SEARCH is returned when the response comes from web search."""
    query = "What is the weather today?"
    chunks = [Mock(chunk_text="Context chunk")]

    mock_final_chain = Mock()
    mock_final_chain.invoke.return_value = "NEED_WEB_SEARCH"

    query_handler._prompt_template.__or__.return_value = query_handler._llm
    query_handler._llm.__or__.return_value = mock_final_chain

    with patch(
        "src.components.chatbot.query_handler.StrOutputParser",
        return_value=Mock(),
    ):
        result = query_handler.generate_responses(query, chunks, from_web_search=True)

    assert result == "NEED_WEB_SEARCH"


def test_generate_responses_no_chunks_returns_none(query_handler):
    """Test response generation handles empty chunk lists."""
    assert query_handler.generate_responses("test query", []) is None
