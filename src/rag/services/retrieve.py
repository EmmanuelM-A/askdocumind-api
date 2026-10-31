import logging
from uuid import UUID

from src.auth.repository.user_repository import UserRepository
from src.chat_session.repository.chat_session_repository import ChatSessionRepository
from src.config.configs import settings
from src.rag.repository.chunk_embedding_repository import ChunkEmbeddingRepository
from src.rag.schemas.retrieval import (
    GetChunkEmbeddings,
    RetrievalResults,
    WebResult,
)
from src.rag.services.embed.embedder import Embedder
from src.rag.services.expand.query_expander import QueryExpander
from src.rag.services.fallback.web_searcher import WebSearcher
from src.rag.services.rerank.reranker import Reranker
from src.shared.services import BaseService

_logger = logging.getLogger(__name__)


class RetrieveChunkEmbeddingService(BaseService):
    def __init__(
        self,
        query_expander: QueryExpander,
        reranker: Reranker,
        web_searcher: WebSearcher,
        embedder: Embedder,
        chunk_embedding_repository: ChunkEmbeddingRepository,
        chat_session_repository: ChatSessionRepository,
        user_repository: UserRepository,
    ) -> None:
        super().__init__(user_repository, chat_session_repository)
        self._query_expander = query_expander
        self._reranker = reranker
        self._web_searcher = web_searcher
        self._embedder = embedder
        self._chunk_embedding_repository = chunk_embedding_repository

    async def retrieve(
        self,
        data: GetChunkEmbeddings,
        chat_session_id: UUID,
        authenticated_user_id: UUID,
    ) -> RetrievalResults:
        """
        Retrieves relevant context based on the provided query and owner ID.
        """
        await self._verify_user_owns_chat_session(
            authenticated_user_id, chat_session_id
        )

        expanded_query = await self._query_expander.expand(data.query)

        query_vector = await self._embedder.embed_query(expanded_query)

        relevant_chunks = await self._chunk_embedding_repository.search_by_similarity(
            chat_session_id=chat_session_id,
            vector=query_vector,
            min_similarity=data.configs.threshold,
            limit=max(data.configs.top_k, settings.rag.MAX_RETRIEVAL_CANDIDATES),
        )

        web_search_needed = (
            len(relevant_chunks) < settings.rag.MIN_CHUNKS_NEEDED_FOR_WEB_SEARCH
        )

        additional_results: list[WebResult] = []

        if web_search_needed and data.configs.web_search_enabled:
            _logger.info("Insufficient relevant chunks found, performing web search...")
            web_content = await self._web_searcher.search_web(expanded_query)
            additional_results.extend(web_content)

        rerank_possible = (
            len(relevant_chunks) >= settings.rag.MIN_CHUNKS_NEEDED_FOR_RERANKING
        )

        if rerank_possible:
            _logger.info("Reranking relevant chunks based on query...")
            relevant_chunks = await self._reranker.rerank(
                query=expanded_query, chunk_embeddings=relevant_chunks
            )

        top_k_relevant_chunks = relevant_chunks[: data.configs.top_k]

        return RetrievalResults(
            chunks=[chunk.viewable() for chunk in top_k_relevant_chunks],
            additional=additional_results,
            expanded_query=expanded_query,
        )
