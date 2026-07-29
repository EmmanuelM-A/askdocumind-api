"""
Responsible for handling user queries and generating their corresponding
response.
"""

from typing import List, Literal, Optional, Tuple, cast
from uuid import UUID

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from src.api.validation.helper import validate_and_sanitize_query
from src.config.configs import settings
from src.config.constants import DocumentSourceType
from src.components.prompts.prompt_loader import create_prompt_template
from src.components.retrieval.embedder import Embedder
from src.components.retrieval.reranker import Reranker
from src.database.models import DocumentChunk
from src.database.repository.interfaces.db_transaction import DBTransaction
from src.database.repository.interfaces.document_chunk_repository import (
    DocumentChunkRepositoryInterface,
)
from src.errors.custom_exceptions import server_error
from src.logger.base_logger import BaseLogger

PossibleResponse = Literal["NEED_WEB_SEARCH", "OUT_OF_SCOPE"] | str | None


class QueryHandler:
    """
    Handles the query processing and the response generation.
    """

    def __init__(
        self,
        embedder: Embedder,
        document_chunk_repo: DocumentChunkRepositoryInterface,
        reranker: Reranker,
    ) -> None:
        """
        Initializes the QueryHandler instance.

        Args:
            embedder: The class instance used to create embeddings for indexes.
            reranker: Reranker used to reorder retrieved chunks by relevance
                before they're used for response generation.
        """
        self.embedder = embedder
        self.document_chunk_repo = document_chunk_repo
        self.reranker = reranker
        self.llm = ChatOpenAI(
            model=settings.llm.LLM_MODEL_NAME,
            temperature=settings.llm.LLM_TEMPERATURE,
            timeout=settings.llm.LLM_REQUEST_TIMEOUT_SECS,
            max_retries=settings.llm.LLM_MAX_RETRIES,
            max_completion_tokens=settings.llm.LLM_MAX_OUTPUT_TOKENS,
        )
        self._prompt_template = create_prompt_template(
            settings.llm.RESPONSE_PROMPT_FILEPATH
        )
        self._logger = BaseLogger(__name__)

    async def search_for_vectors(
        self,
        query: str,
        chat_session_id: UUID,
        source_type: Optional[DocumentSourceType] = None,
        tx: Optional[DBTransaction] = None,
    ) -> Tuple[List[DocumentChunk], List[str]]:
        """
        Embeds query, searches vector DB, returns top_k results.

        `source_type`: optional filter restricting the search to chunks
        belonging to documents of this type (e.g. UPLOAD only, excluding
        previously-ingested web-search content). When None, all chunks for
        the chat session are searched.

        `tx`: optional transaction to run the search under - used so a
        caller can search over rows staged (flushed but not yet committed)
        earlier in the same transaction, e.g. freshly-ingested web content
        that hasn't been committed yet.
        """

        query = validate_and_sanitize_query(query, self._logger)

        self._logger.debug("Embedding queries now...")

        query_vector = self.embedder.embed_query(query)

        self._logger.debug("Initialing vector search...")

        top_k = settings.vector.RETRIEVAL_TOP_K

        chunks: List[DocumentChunk] = await self.document_chunk_repo.search_similar(
            chat_session_id=chat_session_id,
            vector=query_vector,
            top_k=settings.vector.RERANK_CANDIDATE_POOL_SIZE,
            threshold=settings.vector.SIMILARITY_THRESHOLD,
            source_type=source_type,
            tx=tx,
        )

        if chunks:
            self._logger.debug(f"Reranking {len(chunks)} candidate chunks...")
            chunks = await self.reranker.rerank(query=query, chunks=chunks, top_k=top_k)

        sources: List[str] = await self.document_chunk_repo.get_filenames_for_chunks(
            chunks=chunks,
            chat_session_id=chat_session_id,
            tx=tx,
        )

        if not chunks or len(chunks) == 0:
            self._logger.error(
                f"No vector chunks found for the query {query}. Returning empty results."
            )
            return [], []

        self._logger.info(f"Results found for the query: {query}")

        return chunks, sources

    def generate_response(
        self,
        query: str,
        retrieved_chunks: List[DocumentChunk],
        from_web_search: bool = False,
    ) -> PossibleResponse:
        """
        Formats a prompt with the query and retrieved chunks, then passes it
        to an LLM.
        """

        if not retrieved_chunks:
            self._logger.debug(
                "No retrieved chunks provided - asking the LLM to judge scope from the "
                "question alone (empty context)."
            )

        self._logger.debug(f"Generating responses for the query: {query}")

        context_text = "\n\n".join(
            [cast(str, chunk.chunk_text) for chunk in retrieved_chunks]
        )

        rag_chain = self._prompt_template | self.llm | StrOutputParser()

        try:
            response = rag_chain.invoke(
                {"context": context_text, "query": query}
            )
        except Exception as e:
            raise server_error(
                message="The AI service is temporarily unavailable. Please try again shortly.",
                error_code="LLM_SERVICE_ERROR",
                stack_trace=str(e),
            )

        response = response.strip()

        if not response:
            self._logger.warning("LLM returned an empty response.")
            return None

        if response == "NEED_WEB_SEARCH" and not from_web_search:
            self._logger.info(
                "LLM indicated that a web search is needed for the query."
            )
            return response

        self._logger.debug("Response generated by LLM.")

        return response
