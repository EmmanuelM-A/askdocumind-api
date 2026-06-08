"""
Responsible for wrapping the embedding model client to encode text into
vectors.
"""

from typing import Dict, Any, List, Iterable, Iterator

from langchain_openai import OpenAIEmbeddings

from src.config.configs import settings
from src.errors.custom_exceptions import server_error
from src.logger.base_logger import BaseLogger


class Embedder:
    """
    Handles text embedding by processing documents and converting them into
    embedding vectors using a specified embedding model with caching support.
    """

    def __init__(self):
        self._logger = BaseLogger(__name__)

        try:
            self.embedding_model = OpenAIEmbeddings(
                model=settings.llm.EMBEDDING_MODEL_NAME
            )
            self._logger.info(
                f"Initialized embedder with the model: {settings.llm.EMBEDDING_MODEL_NAME}"
            )
        except Exception as e:
            raise server_error(
                message="Failed to initialize the embedding model.",
                error_code="EMBEDDER_INIT_ERROR",
                stack_trace=str(e),
            )

    def embed_documents(self, documents: Iterable[str]) -> Iterator[List[List[float]]]:
        """
        Incrementally embed documents in batches.

        This method is designed for memory-efficient pipelines where
        documents are streamed (e.g. from a generator).

        Args:
            documents: Iterable of document text strings.

        Yields:
            Batch of embedding vectors (List[List[float]]).
        """

        buffer_docs: list[str] = []

        for doc in documents:
            buffer_docs.append(doc)

            if len(buffer_docs) >= settings.vector.VECTOR_BATCH_SIZE:
                self._logger.debug(f"Yielding {len(buffer_docs)} vectors")
                yield self._embed_batch(buffer_docs)
                buffer_docs.clear()

        # Flush remainder
        if buffer_docs:
            yield self._embed_batch(buffer_docs)

    def embed_query(self, query: str) -> List[float]:
        """
        Embed a single query string with caching.

        Args:
            query:  The query string to embed.

        Returns:
            The embedding vector for the query.

        Raises:
            Server error if query embedding fails.
        """

        if not query or not query.strip():
            raise server_error(
                message="Query is empty or contains only whitespace.",
                error_code="NO_QUERY_PROVIDED",
            )

        query = query.strip()

        try:
            embedding = self.embedding_model.embed_query(query)
            self._logger.info(f"The query '{query}' has been embedded successfully.")
            return embedding

        except Exception as e:
            raise server_error(
                message="Failed to embed query.",
                error_code="EMBEDDER_EMBED_QUERY_ERROR",
                stack_trace=str(e),
            )

    # ========================= HELPER METHODS =========================

    def _embed_batch(
        self,
        documents: list[str],
    ) -> List[List[float]]:
        """
        Embeds a single batch of documents.

        Args:
            documents: The list of document text strings to embed.

        Returns:
            List of embedding vectors.
        """

        try:
            return self.embedding_model.embed_documents(documents)
        except Exception as e:
            raise server_error(
                message="Failed to get embeddings from model.",
                error_code="EMBEDDING_ERROR",
                stack_trace=str(e),
            )

    def health_check(self) -> Dict[str, Any]:
        """Perform health check on the embedder."""

        return {
            "embedder_status": "healthy" if self.embedding_model else "unhealthy",
            "model_name": getattr(self.embedding_model, "model", "unknown"),
        }
