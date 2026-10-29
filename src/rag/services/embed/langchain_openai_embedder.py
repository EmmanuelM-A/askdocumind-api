from langchain_openai import OpenAIEmbeddings
from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

from src.config.configs import settings
from src.exceptions import (
    ApiException,
    bad_request_error,
    server_error,
    service_unavailable_error,
)
from src.rag.services.chunk.chunker import Chunk
from src.rag.services.embed.embedder import Embedder


def _handle_openai_exception(
    exception: Exception, fallback_message: str, fallback_error_code: str
) -> ApiException:
    """
    Handle exceptions raised by the OpenAI API and raise appropriate
    ApiException with meaningful messages and error codes.
    """
    if isinstance(
        exception, (AuthenticationError, PermissionDeniedError, NotFoundError)
    ):
        return server_error(
            message="An error occurred with the OpenAI embedder's configuration.",
            error_code="EMBEDDER_CONFIG_ERROR",
            cause=exception,
        )

    if isinstance(exception, (BadRequestError, UnprocessableEntityError)):
        return server_error(
            message="The OpenAI embedder rejected the input.",
            error_code="INPUT_REJECTED",
            cause=exception,
        )

    if isinstance(exception, (RateLimitError, APIConnectionError, APIStatusError)):
        return service_unavailable_error(
            message="The embedding service is temporarily unavailable.",
            error_code="EMBEDDER_UNAVAILABLE",
            cause=exception,
        )

    return server_error(
        message=fallback_message,
        error_code=fallback_error_code,
        cause=exception,
    )


class LangChainOpenAIEmbedder(Embedder):
    """
    An implementation of the Embedder interface using LangChain's
    OpenAIEmbeddings.
    """

    def __init__(self):
        try:
            self._model = OpenAIEmbeddings(
                api_key=settings.llm.OPENAI_API_KEY,
                model=settings.rag.EMBEDDING_MODEL,
                timeout=settings.rag.EMBEDDING_REQUEST_TIMEOUT_SECS,
                max_retries=settings.rag.EMBEDDING_MAX_RETRIES,
            )
        except Exception as e:
            raise server_error(
                message="Failed to initialize OpenAI embeddings model.",
                error_code="EMBEDDER_INIT_ERROR",
                cause=e,
            )

    async def embed_chunks(self, chunks: list[Chunk]) -> list[list[float]]:
        if not chunks:
            return []

        try:
            texts = [chunk.text for chunk in chunks]
            return await self._model.aembed_documents(texts)
        except Exception as e:
            raise _handle_openai_exception(
                fallback_message="Failed to embed chunks.",
                fallback_error_code="CHUNK_EMBBEDDING_ERROR",
                exception=e,
            )

    async def embed_query(self, query: str) -> list[float]:
        if not query or not query.strip():
            raise bad_request_error(
                message="Cannot embed an empty query string.",
                error_code="QUERY_REQUIRED",
            )

        try:
            return await self._model.aembed_query(query)
        except Exception as e:
            raise _handle_openai_exception(
                fallback_message="Failed to embed query.",
                fallback_error_code="QUERY_EMBEDDING_ERROR",
                exception=e,
            )
