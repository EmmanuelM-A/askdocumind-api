"""
Responsible for wrapping the embedding model client to encode text into
vectors.
"""

from typing import Dict, Any, List, Tuple, Optional, Iterable, Iterator

from langchain_openai import OpenAIEmbeddings

from src.config.configs import settings
from src.config.constants import CacheNamespace
from src.errors.custom_exceptions import throw_server_error
from src.logger.base_logger import BaseLogger
from src.components.ingestion.document import FileDocument
from src.services.caching.cache_factory import CacheFactory
from src.utils.helper import generate_content_hash


class Embedder:
    """
    Handles text embedding by processing documents and converting them into
    embedding vectors using a specified embedding model with caching support.
    """

    def __init__(self):
        """Initialize the embedder with caching and the embedding model."""

        self._logger = BaseLogger(__name__)

        # Initialize cache
        self.documents_cache = CacheFactory.get_cache(CacheNamespace.DOCUMENTS)
        self.queries_cache = CacheFactory.get_cache(CacheNamespace.QUERIES)

        # Initialize embedding model
        try:
            self.embedding_model = OpenAIEmbeddings(
                model=settings.llm.EMBEDDING_MODEL_NAME
            )
            self._logger.info(
                f"Initialized embedder with the model: {settings.llm.EMBEDDING_MODEL_NAME}"
            )
        except Exception as e:
            throw_server_error(
                message="Failed to initialize the embedding model.",
                error_code="EMBEDDER_INIT_ERROR",
                stack_trace=str(e),
            )

    def embed_documents(
        self, documents: Iterable[FileDocument]
    ) -> Iterator[Tuple[list[list[float]], list[dict]]]:
        """
        Incrementally embed documents in batches.

        This method is designed for memory-efficient pipelines where
        documents are streamed (e.g. from a generator).

        Yields:
            Tuple of (vectors, metadata_batch)
        """

        buffer_docs: list[FileDocument] = []

        for doc in documents:
            buffer_docs.append(doc)

            if len(buffer_docs) >= settings.vector.VECTOR_BATCH_SIZE:
                yield self._embed_batch(buffer_docs)
                buffer_docs.clear()

        # Flush remainder
        if buffer_docs:
            yield self._embed_batch(buffer_docs)

    def embed_query(self, query: str) -> Optional[List[float]]:
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
            throw_server_error(
                message="Query is empty or contains only whitespace.",
                error_code="NO_QUERY_PROVIDED",
            )

        query = query.strip()

        try:
            # Check cache first
            cache_key = self._get_cache_key(query)
            cached = self.queries_cache.get(cache_key)

            if cached is not None:
                self._logger.debug("Cache hit! Using cached query embedding.")
                return cached

            # Get new embedding
            self._logger.debug("Cache miss. Computing new embedding for query.")
            embedding = self.embedding_model.embed_query(query)

            # Cache the result
            self.queries_cache.set(cache_key, embedding)

            self._logger.info(f"The query {query} has been embedded and cached successfully.")

            return embedding

        except Exception as e:
            throw_server_error(
                message="Failed to embed query.",
                error_code="EMBEDDER_EMBED_QUERY_ERROR",
                stack_trace=str(e),
            )
            return None

    # ========================= HELPER METHODS =========================

    def _embed_batch(
        self,
        documents: list[FileDocument],
    ) -> Tuple[list[list[float]], list[dict]]:
        """
        Embeds a single batch of documents.

        :param documents: The list of documents to embed.
        :return: Tuple of (vectors, metadata)
        """

        # Separate cached and uncached content
        cached_embeddings, uncached_items = self._get_cached_document_embeddings(
            documents
        )

        # Get new embeddings for uncached items
        new_embeddings = self._get_new_document_embeddings(uncached_items)

        # Combine cached and new embeddings
        vectors = self._combine_embeddings(
            cached_embeddings,
            new_embeddings,
            len(documents),
        )

        metadata = [doc.metadata.to_dict() for doc in documents]

        return vectors, metadata

    @staticmethod
    def _get_cache_key(content: str) -> str:
        """
        Generate cache key from content.

        Args:
            content: The text content.

        Returns:
            Cache key string.
        """
        return f"{generate_content_hash(content)}"

    def _get_cached_document_embeddings(
        self, documents: List[FileDocument]
    ) -> Tuple[List[Tuple[int, List[float]]], List[Tuple[int, str, str]]]:
        """
        Get cached document embeddings and identify uncached items.

        Args:
            documents: List of documents to check cache for.

        Returns:
            Tuple of:
                - List of (index, embedding) for cached items.
                - List of (index, content, source) for uncached items.
        """
        cached_doc_embeddings = []
        uncached_items = []

        for i, doc in enumerate(documents):
            cache_key = self._get_cache_key(doc.content)
            cached = self.documents_cache.get(cache_key)

            if cached is not None:
                cached_doc_embeddings.append((i, cached))
            else:
                uncached_items.append(
                    (i, doc.content, doc.metadata.source or "unknown")
                )

        cache_hit_rate = (
            len(cached_doc_embeddings) / len(documents) * 100 if documents else 0
        )
        self._logger.debug(
            f"Cache hit rate: {cache_hit_rate:.1f}% "
            f"({len(cached_doc_embeddings)}/{len(documents)})"
        )

        return cached_doc_embeddings, uncached_items

    def _get_new_document_embeddings(
        self, uncached_items: List[Tuple[int, str, str]]
    ) -> Optional[List[Tuple[int, List[float]]]]:
        """
        Get embeddings for uncached items and store them in cache.

        Args:
            uncached_items: List of (index, content, source) tuples.

        Returns:
            List of (index, embedding) tuples.
        """
        if not uncached_items:
            return []

        self._logger.debug(f"Computing embeddings for {len(uncached_items)} new items")

        # Extract texts for batch embedding
        texts = [item[1] for item in uncached_items]

        try:
            # Get embeddings in batch from OpenAI
            new_embeddings = self.embedding_model.embed_documents(texts)

            # Store in cache and create result list
            result = []
            for (original_idx, text, _), embedding in zip(
                uncached_items, new_embeddings
            ):
                # Cache the embedding
                cache_key = self._get_cache_key(text)
                self.documents_cache.set(
                    cache_key,
                    embedding,
                )
                result.append((original_idx, embedding))

            self._logger.info("Cached new document embeddings successfully.")

            return result

        except Exception as e:
            throw_server_error(
                message="Failed to get embeddings from model.",
                error_code="EMBEDDING_ERROR",
                stack_trace=str(e),
            )
            return None

    @staticmethod
    def _combine_embeddings(
        cached_embeddings: List[Tuple[int, List[float]]],
        new_embeddings: List[Tuple[int, List[float]]],
        total_count: int,
    ) -> List[List[float]] | List[None]:
        """
        Combine cached and new embeddings in correct order.

        Args:
            cached_embeddings: List of (index, embedding) for cached items.
            new_embeddings: List of (index, embedding) for new items.
            total_count: Total number of embeddings expected.

        Returns:
            List of embeddings in correct order.

        Raises:
            Server error if embeddings cannot be combined.
        """
        vectors = [None] * total_count

        # Place cached embeddings
        for idx, embedding in cached_embeddings:
            vectors[idx] = embedding

        # Place new embeddings
        for idx, embedding in new_embeddings:
            vectors[idx] = embedding

        # Verify all positions are filled
        if None in vectors:
            missing_indices = [i for i, v in enumerate(vectors) if v is None]
            throw_server_error(
                message="Failed to combine embeddings. Some positions are missing.",
                error_code="EMBEDDER_COMBINE_ERROR",
                error_details=f"Missing indices: {missing_indices}",
            )

        return vectors

    # ========================= CACHE MANAGEMENT =========================

    def clear_caches(self) -> None:
        """Clear the embedding cache."""

        self.documents_cache.clear()
        self.queries_cache.clear()
        self._logger.info("Cleared embedder caches successfully.")

    def health_check(self) -> Dict[str, Any]:
        """Perform health check on the embedder."""

        return {
            "embedder_status": "healthy" if self.embedding_model else "unhealthy",
            "model_name": getattr(self.embedding_model, "model", "unknown"),
        }
