from typing import List

from langchain_openai import OpenAIEmbeddings

from src.config.configs import settings
from src.exceptions import server_error, bad_request_error, service_unavailable_error
from src.rag.services.chunk.chunker import Chunk
from src.rag.services.embed.embedder import Embedder


class LangChainOpenAIEmbedder(Embedder):

    def __init__(self):
        try:
            self._model = OpenAIEmbeddings(
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

    async def embed_chunks(self, chunks: List[Chunk]) -> List[List[float]]:
        if not chunks:
            return []

        try:
            texts = [chunk.text for chunk in chunks]
            return self._model.embed_documents(texts)
        except Exception as e:
            raise service_unavailable_error(
                message="Failed to embed chunks. The embedding service may be unavailable.",
                error_code="EMBED_CHUNKS_ERROR",
                cause=e,
            )

    async def embed_query(self, query: str) -> List[float]:
        if not query or not query.strip():
            raise bad_request_error(
                message="Cannot embed an empty query string.",
                error_code="QUERY_REQUIRED",
            )

        try:
            return self._model.embed_query(query)
        except Exception as e:
            raise service_unavailable_error(
                message="Failed to embed query. The embedding service may be unavailable.",
                error_code="EMBED_QUERY_ERROR",
                cause=e,
            )
