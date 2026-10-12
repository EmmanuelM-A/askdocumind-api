import logging
from math import sqrt
from uuid import UUID

from src.config.configs import settings
from src.rag.models.chunk_embedding import ChunkEmbedding
from src.rag.models.mapper import ViewableChunkEmbedding
from src.rag.repository.chunk_embedding_repository import ChunkEmbeddingRepository
from src.rag.schemas.retrieval import GetChunkEmbeddings
from src.rag.services.embed.embedder import Embedder
from src.rag.services.expand.query_expander import QueryExpander
from src.rag.services.fallback.web_searcher import WebSearcher
from src.rag.services.rerank.reranker import Reranker

_logger = logging.getLogger(__name__)


class RetrieveChunkEmbeddingService:

    def __init__(
        self,
        query_expander: QueryExpander,
        reranker: Reranker,
        web_searcher: WebSearcher,
        embedder: Embedder,
        chunk_embedding_repository: ChunkEmbeddingRepository,
    ) -> None:
        self._query_expander = query_expander
        self._reranker = reranker
        self._web_searcher = web_searcher
        self._embedder = embedder
        self._chunk_embedding_repository = chunk_embedding_repository

    async def _similarity_search(
        self,
        chat_session_id: UUID,
        vector: list[float],
        threshold: float = 0.7,
    ) -> list[ChunkEmbedding]:
        """
        Performs a similarity search for chunk embeddings based on the provided
        vector.
        """
        if vector is None:
            return []

        candidates = (
            await self._chunk_embedding_repository.get_candidate_chunk_embeddings(
                chat_session_id=chat_session_id
            )
        )

        vector_norm = sqrt(sum(x * x for x in vector))

        if vector_norm == 0:
            return []

        scores: list[tuple[float, ChunkEmbedding]] = []

        for candidate in candidates:
            embedding = candidate.embedding

            if embedding is None:
                continue

            embedding_as_list = embedding.tolist()

            embedding_norm = sqrt(sum(x * x for x in embedding_as_list))

            if embedding_norm == 0:
                continue

            dot_product = sum(x * y for x, y in zip(vector, embedding_as_list))

            similarity = dot_product / (vector_norm * embedding_norm)

            if similarity >= threshold:
                scores.append((similarity, candidate))

        # Sort by similarity in descending order
        scores.sort(key=lambda x: x[0], reverse=True)

        return [chunk for _, chunk in scores]

    async def retrieve(
        self, data: GetChunkEmbeddings, chat_session_id: UUID
    ) -> tuple[list[ViewableChunkEmbedding], list[str]]:
        """
        Retrieves relevant context based on the provided query and owner ID.
        """
        expanded_query = await self._query_expander.expand(data.query)

        query_vector = await self._embedder.embed_query(expanded_query)

        relevant_chunks: list[ChunkEmbedding] = await self._similarity_search(
            chat_session_id=chat_session_id,
            vector=query_vector,
            threshold=data.configs.threshold,
        )

        web_search_needed = (
            len(relevant_chunks) < settings.rag.MIN_CHUNKS_NEEDED_FOR_WEB_SEARCH
        )

        additional_results: list[str] = []

        if web_search_needed and data.configs.web_search_enabled:
            _logger.info("Insufficient relevant chunks found, performing web search...")
            web_content = await self._web_searcher.search_web(expanded_query)
            additional_results.extend(web_content)

        rerank_possible = (
            len(relevant_chunks) > settings.rag.MIN_CHUNKS_NEEDED_FOR_RERANKING
        )

        if rerank_possible:
            _logger.info("Reranking relevant chunks based on query...")
            relevant_chunks = await self._reranker.rerank(
                query=expanded_query, chunk_embeddings=relevant_chunks
            )

        top_k_relevant_chunks = relevant_chunks[: data.configs.top_k]

        return [chunk.viewable() for chunk in top_k_relevant_chunks], additional_results
