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
        mock_prompt.side_effect = [Mock(), Mock()]

        handler = QueryHandler(
            embedder=mock_embedder,
            document_chunk_repo=mock_document_chunk_repo,
        )

    assert handler.embedder is mock_embedder
    assert handler.document_chunk_repo is mock_document_chunk_repo
    assert handler._llm is not None
    assert handler._prompt_template is not None
    assert handler._expansion_prompt_template is not None
    assert handler._prompt_template is not handler._expansion_prompt_template


# ==================== SEARCH FOR VECTORS TESTS ====================


@pytest.mark.asyncio
async def test_search_for_vectors_success(query_handler):
    """Test successful vector search: a candidate pool is fetched, reranked,
    then used to look up sources."""
    chat_session_id = uuid4()
    candidate_chunks = [Mock(chunk_text=f"Chunk {i}") for i in range(5)]
    reranked_chunks = [candidate_chunks[3], candidate_chunks[0]]

    query_handler.reranker.rerank = AsyncMock(return_value=reranked_chunks)
    query_handler.document_chunk_repo.search_similar = AsyncMock(
        return_value=candidate_chunks
    )
    query_handler.document_chunk_repo.get_filenames_for_chunks = AsyncMock(
        return_value=["doc4.txt", "doc1.txt"]
    )

    with patch(
        "src.components.chatbot.query_handler.validate_and_sanitize_query",
        return_value="sanitized query",
    ) as mock_validate, patch(
        "src.components.chatbot.query_handler.settings"
    ) as mock_settings:
        mock_settings.vector.RETRIEVAL_TOP_K = 2
        mock_settings.vector.RERANK_CANDIDATE_POOL_SIZE = 15
        mock_settings.vector.SIMILARITY_THRESHOLD = 0.4

        result = await query_handler.search_for_vectors("  test query  ", chat_session_id)

    assert result == (reranked_chunks, ["doc4.txt", "doc1.txt"])
    mock_validate.assert_called_once()
    query_handler.embedder.embed_query.assert_called_once_with("sanitized query")
    query_handler.document_chunk_repo.search_similar.assert_awaited_once_with(
        chat_session_id=chat_session_id,
        vector=[0.1, 0.2, 0.3, 0.4, 0.5],
        top_k=15,
        threshold=0.4,
    )
    query_handler.reranker.rerank.assert_awaited_once_with(
        query="sanitized query", chunks=candidate_chunks, top_k=2
    )
    query_handler.document_chunk_repo.get_filenames_for_chunks.assert_awaited_once_with(
        chunks=reranked_chunks,
        chat_session_id=chat_session_id,
    )


@pytest.mark.asyncio
async def test_search_for_vectors_empty_query_raises_error(query_handler):
    """Test empty queries are rejected by validation."""
    with pytest.raises(ApiException) as exc_info:
        await query_handler.search_for_vectors("   ", uuid4())

    assert exc_info.value.error.code == "EMPTY_QUERY"


@pytest.mark.asyncio
async def test_search_for_vectors_no_results_returns_empty(query_handler):
    """Test search returns empty lists when no chunks are found, and the
    reranker is skipped since there's nothing to rerank."""
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
        mock_settings.vector.RERANK_CANDIDATE_POOL_SIZE = 15
        mock_settings.vector.SIMILARITY_THRESHOLD = 0.7

        result = await query_handler.search_for_vectors("test query", chat_session_id)

    assert result == ([], [])
    query_handler.document_chunk_repo.search_similar.assert_awaited_once()
    query_handler.reranker.rerank.assert_not_called()
    query_handler.document_chunk_repo.get_filenames_for_chunks.assert_awaited_once()


# ==================== GENERATE RESPONSE TESTS ====================


def test_generate_response_success(query_handler):
    """Test successful response generation, including that the *expanded*
    query (not the raw input query) is what actually reaches the LLM."""
    query = "What is the test content?"
    chunks = [Mock(chunk_text="First chunk content"), Mock(chunk_text="Second chunk content")]

    mock_final_chain = Mock()
    mock_final_chain.invoke.return_value = "This is the answer based on the context."

    query_handler._prompt_template.__or__.return_value = query_handler._llm
    query_handler._llm.__or__.return_value = mock_final_chain

    with patch(
        "src.components.chatbot.query_handler.StrOutputParser",
        return_value=Mock(),
    ), patch(
        "src.components.chatbot.query_handler.expand_query",
        return_value="expanded query text",
    ) as mock_expand:
        result = query_handler.generate_response(query, chunks)

    assert result == "This is the answer based on the context."
    mock_expand.assert_called_once_with(
        query=query,
        llm=query_handler._llm,
        prompt_template=query_handler._expansion_prompt_template,
    )
    call_args = mock_final_chain.invoke.call_args[0][0]
    assert call_args["query"] == "expanded query text"
    assert call_args["context"] == "First chunk content\n\nSecond chunk content"


def test_generate_response_need_web_search(query_handler):
    """Test response generation returns NEED_WEB_SEARCH when the LLM signals it."""
    query = "What is the weather today?"
    chunks = [Mock(chunk_text="Context chunk")]

    mock_final_chain = Mock()
    mock_final_chain.invoke.return_value = "NEED_WEB_SEARCH"

    query_handler._prompt_template.__or__.return_value = query_handler._llm
    query_handler._llm.__or__.return_value = mock_final_chain

    with patch(
        "src.components.chatbot.query_handler.StrOutputParser",
        return_value=Mock(),
    ), patch(
        "src.components.chatbot.query_handler.expand_query",
        return_value=query,
    ):
        result = query_handler.generate_response(query, chunks)

    assert result == "NEED_WEB_SEARCH"


def test_generate_response_need_web_search_already_from_web(query_handler):
    """Test NEED_WEB_SEARCH is still returned (just via the non-web-search
    log branch) when the response already came from a web search."""
    query = "What is the weather today?"
    chunks = [Mock(chunk_text="Context chunk")]

    mock_final_chain = Mock()
    mock_final_chain.invoke.return_value = "NEED_WEB_SEARCH"

    query_handler._prompt_template.__or__.return_value = query_handler._llm
    query_handler._llm.__or__.return_value = mock_final_chain

    with patch(
        "src.components.chatbot.query_handler.StrOutputParser",
        return_value=Mock(),
    ), patch(
        "src.components.chatbot.query_handler.expand_query",
        return_value=query,
    ):
        result = query_handler.generate_response(query, chunks, from_web_search=True)

    assert result == "NEED_WEB_SEARCH"


def test_generate_response_no_chunks_returns_none(query_handler):
    """Test response generation handles empty chunk lists without calling the LLM."""
    assert query_handler.generate_response("test query", []) is None


def test_generate_response_llm_service_error(query_handler):
    """Test that an LLM invocation failure is wrapped as a 500 server error."""
    chunks = [Mock(chunk_text="Some content")]

    mock_final_chain = Mock()
    mock_final_chain.invoke.side_effect = Exception("LLM is down")

    query_handler._prompt_template.__or__.return_value = query_handler._llm
    query_handler._llm.__or__.return_value = mock_final_chain

    with patch(
        "src.components.chatbot.query_handler.StrOutputParser",
        return_value=Mock(),
    ), patch(
        "src.components.chatbot.query_handler.expand_query",
        return_value="expanded query",
    ):
        with pytest.raises(ApiException) as exc_info:
            query_handler.generate_response("query", chunks)

    assert exc_info.value.error.code == "LLM_SERVICE_ERROR"


def test_generate_response_empty_llm_response_returns_none(query_handler):
    """Test that a whitespace-only LLM response results in None, not an empty string."""
    chunks = [Mock(chunk_text="Some content")]

    mock_final_chain = Mock()
    mock_final_chain.invoke.return_value = "   "

    query_handler._prompt_template.__or__.return_value = query_handler._llm
    query_handler._llm.__or__.return_value = mock_final_chain

    with patch(
        "src.components.chatbot.query_handler.StrOutputParser",
        return_value=Mock(),
    ), patch(
        "src.components.chatbot.query_handler.expand_query",
        return_value="expanded query",
    ):
        result = query_handler.generate_response("query", chunks)

    assert result is None
