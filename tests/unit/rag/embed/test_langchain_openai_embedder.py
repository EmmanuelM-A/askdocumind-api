# Tests for LangChainOpenAIEmbedder. The real OpenAIEmbeddings class is constructed with a fake
# API key, and only its async network calls (aembed_documents and aembed_query) are patched.

import inspect
import uuid
from unittest.mock import AsyncMock, patch
from uuid import UUID

import httpx
import pytest
from langchain_openai import OpenAIEmbeddings
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

from src.config.configs import settings
from src.exceptions import ApiException
from src.rag.services.chunk.chunker import Chunk
from src.rag.services.embed.embedder import Embedder
from src.rag.services.embed.langchain_openai_embedder import LangChainOpenAIEmbedder

pytestmark = pytest.mark.asyncio

EMBEDDER_MODULE = "src.rag.services.embed.langchain_openai_embedder"
REQUEST = httpx.Request("POST", "https://api.openai.com/v1/embeddings")


def make_chunk(text: str, source: UUID, index: int = 0) -> Chunk:
    start = index * 1000
    return Chunk(
        text=text,
        index=index,
        source=source,
        start_offset=start,
        end_offset=start + len(text),
    )


def status_error(error_class, status, code=None):
    response = httpx.Response(status, request=REQUEST)
    body = {"code": code} if code else None
    return error_class("failure", response=response, body=body)


_REQUEST = httpx.Request("POST", "https://api.openai.com/v1/embeddings")


def _status_error(error_class, status, code=None):
    response = httpx.Response(status, request=_REQUEST)
    body = {"code": code} if code else None
    return error_class("failure", response=response, body=body)


CHUNK_CASES = [
    (_status_error(AuthenticationError, 401), 500),
    (_status_error(PermissionDeniedError, 403), 500),
    (_status_error(NotFoundError, 404), 500),
    (_status_error(BadRequestError, 400), 500),
    (_status_error(RateLimitError, 429), 503),
    (_status_error(RateLimitError, 429, "insufficient_quota"), 500),
    (_status_error(InternalServerError, 503), 503),
    (APIConnectionError(request=_REQUEST), 503),
    (APITimeoutError(request=_REQUEST), 503),
    (ValueError("bug"), 500),
]

ERROR_CASES = [
    pytest.param(status_error(AuthenticationError, 401), 500, id="authentication"),
    pytest.param(status_error(PermissionDeniedError, 403), 500, id="permission-denied"),
    pytest.param(status_error(NotFoundError, 404), 500, id="not-found"),
    pytest.param(status_error(BadRequestError, 400), 500, id="bad-request"),
    pytest.param(status_error(UnprocessableEntityError, 422), 500, id="unprocessable"),
    pytest.param(status_error(RateLimitError, 429), 503, id="rate-limit"),
    pytest.param(
        status_error(RateLimitError, 429, "insufficient_quota"),
        503,
        id="quota-exhausted",
    ),
    pytest.param(status_error(InternalServerError, 503), 503, id="provider-outage"),
    pytest.param(status_error(ConflictError, 409), 503, id="conflict"),
    pytest.param(status_error(APIStatusError, 418), 503, id="other-status"),
    pytest.param(APIConnectionError(request=REQUEST), 503, id="connection"),
    pytest.param(APITimeoutError(request=REQUEST), 503, id="timeout"),
    pytest.param(ValueError("bug"), 500, id="value-error"),
    pytest.param(RuntimeError("bug"), 500, id="runtime-error"),
    pytest.param(KeyError("bug"), 500, id="key-error"),
]


@pytest.fixture(autouse=True)
def fake_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


@pytest.fixture
def embedder() -> LangChainOpenAIEmbedder:
    return LangChainOpenAIEmbedder()


@pytest.fixture
def aembed_documents():
    with patch.object(
        OpenAIEmbeddings, "aembed_documents", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
def aembed_query():
    with patch.object(OpenAIEmbeddings, "aembed_query", new_callable=AsyncMock) as mock:
        yield mock


class TestContract:
    def test_is_an_embedder(self, embedder):
        assert isinstance(embedder, Embedder)

    @pytest.mark.parametrize("method", ["embed_chunks", "embed_query"])
    def test_methods_are_coroutines(self, embedder, method):
        assert inspect.iscoroutinefunction(getattr(embedder, method))


class TestInitialization:
    def test_builds_real_model(self, embedder):
        assert isinstance(embedder._model, OpenAIEmbeddings)

    def test_model_receives_settings(self):
        with patch(f"{EMBEDDER_MODULE}.OpenAIEmbeddings") as model_class:
            LangChainOpenAIEmbedder()

        model_class.assert_called_once_with(
            model=settings.rag.EMBEDDING_MODEL,
            timeout=settings.rag.EMBEDDING_REQUEST_TIMEOUT_SECS,
            max_retries=settings.rag.EMBEDDING_MAX_RETRIES,
        )

    def test_missing_api_key_raises_server_error(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ApiException) as exc:
            LangChainOpenAIEmbedder()

        assert exc.value.status_code == 500

    def test_model_construction_failure_raises_server_error(self):
        with patch(
            f"{EMBEDDER_MODULE}.OpenAIEmbeddings", side_effect=Exception("bad config")
        ):
            with pytest.raises(ApiException) as exc:
                LangChainOpenAIEmbedder()

        assert exc.value.status_code == 500


class TestEmbedChunks:
    async def test_passes_chunk_texts_to_model(self, embedder, aembed_documents):
        aembed_documents.return_value = [[0.1, 0.2], [0.3, 0.4]]
        source = uuid.uuid4()
        chunks = [
            make_chunk("hello world", source, 0),
            make_chunk("goodbye world", source, 1),
        ]

        result = await embedder.embed_chunks(chunks)

        aembed_documents.assert_awaited_once_with(["hello world", "goodbye world"])
        assert result == [[0.1, 0.2], [0.3, 0.4]]

    async def test_empty_list_returns_empty_without_calling_model(
        self, embedder, aembed_documents
    ):
        assert await embedder.embed_chunks([]) == []
        aembed_documents.assert_not_called()

    async def test_single_chunk(self, embedder, aembed_documents):
        aembed_documents.return_value = [[0.5]]

        result = await embedder.embed_chunks([make_chunk("only", uuid.uuid4())])

        assert result == [[0.5]]
        aembed_documents.assert_awaited_once_with(["only"])

    async def test_preserves_order(self, embedder, aembed_documents):
        aembed_documents.return_value = [[1.0], [2.0], [3.0]]
        source = uuid.uuid4()
        chunks = [make_chunk(text, source, i) for i, text in enumerate("abc")]

        result = await embedder.embed_chunks(chunks)

        assert result == [[1.0], [2.0], [3.0]]
        aembed_documents.assert_awaited_once_with(["a", "b", "c"])

    async def test_sends_only_text_not_metadata(self, embedder, aembed_documents):
        aembed_documents.return_value = [[0.1]]
        chunk = make_chunk("body", uuid.uuid4())
        chunk.metadata["page"] = 3

        await embedder.embed_chunks([chunk])

        aembed_documents.assert_awaited_once_with(["body"])

    async def test_unicode_and_blank_text_are_passed_through(
        self, embedder, aembed_documents
    ):
        aembed_documents.return_value = [[0.1], [0.2]]
        source = uuid.uuid4()
        chunks = [make_chunk("héllo 你好 🚀", source, 0), make_chunk("", source, 1)]

        await embedder.embed_chunks(chunks)

        aembed_documents.assert_awaited_once_with(["héllo 你好 🚀", ""])

    async def test_large_batch_is_sent_in_one_call(self, embedder, aembed_documents):
        source = uuid.uuid4()
        chunks = [make_chunk(f"chunk {i}", source, i) for i in range(500)]
        aembed_documents.return_value = [[float(i)] for i in range(500)]

        result = await embedder.embed_chunks(chunks)

        aembed_documents.assert_awaited_once()
        assert len(result) == 500

    @pytest.mark.parametrize("error, expected_status", ERROR_CASES)
    async def test_model_failure_maps_to_status(
        self, embedder, aembed_documents, error, expected_status
    ):
        aembed_documents.side_effect = error

        with pytest.raises(ApiException) as exc:
            await embedder.embed_chunks([make_chunk("hello", uuid.uuid4())])

        assert exc.value.status_code == expected_status


class TestEmbedQuery:
    async def test_passes_query_to_model(self, embedder, aembed_query):
        aembed_query.return_value = [0.5, 0.6]

        result = await embedder.embed_query("hello world")

        aembed_query.assert_awaited_once_with("hello world")
        assert result == [0.5, 0.6]

    async def test_query_is_not_stripped_before_embedding(self, embedder, aembed_query):
        aembed_query.return_value = [0.1]

        await embedder.embed_query("  padded  ")

        aembed_query.assert_awaited_once_with("  padded  ")

    async def test_unicode_query(self, embedder, aembed_query):
        aembed_query.return_value = [0.1]

        await embedder.embed_query("héllo 你好 🚀")

        aembed_query.assert_awaited_once_with("héllo 你好 🚀")

    @pytest.mark.parametrize("bad_query", ["", " ", "   ", "\t\n", None])
    async def test_empty_or_blank_query_is_bad_request(
        self, embedder, aembed_query, bad_query
    ):
        with pytest.raises(ApiException) as exc:
            await embedder.embed_query(bad_query)

        assert exc.value.status_code == 400
        aembed_query.assert_not_called()

    @pytest.mark.parametrize("error, expected_status", ERROR_CASES)
    async def test_model_failure_maps_to_status(
        self, embedder, aembed_query, error, expected_status
    ):
        aembed_query.side_effect = error

        with pytest.raises(ApiException) as exc:
            await embedder.embed_query("hello world")

        assert exc.value.status_code == expected_status
