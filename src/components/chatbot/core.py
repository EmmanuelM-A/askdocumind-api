"""
Handles chatbot interactions using Retrieval-Augmented Generation (RAG).
"""

import json
from dataclasses import dataclass
from typing import List
from uuid import UUID

from src.components.chatbot.query_handler import PossibleResponse, QueryHandler
from src.components.ingestion.document_processor import (
    UploadedDocumentProcessor,
)
from src.components.retrieval.embedder import Embedder
from src.components.retrieval.web_searcher import WebSearcher
from src.config.configs import settings
from src.database.repository.interfaces import DBTransactionFactory
from src.database.repository.interfaces.document_chunk_repository import (
    DocumentChunkRepositoryInterface,
)
from src.logger.base_logger import BaseLogger


@dataclass
class ChatbotResponse:
    answer: str
    sources: List[str]

    def to_dict(self) -> dict:
        """Return a JSON-serializable dictionary representation."""
        return {
            "answer": self.answer,
            "sources": self.sources,
        }

    def to_json(self) -> str:
        """Return a JSON string representation."""
        return json.dumps(self.to_dict(), indent=4)


class RAGChatbot:
    """Defines all methods related to RAG Chatbot interactions."""

    def __init__(
        self,
        document_processor: UploadedDocumentProcessor,
        embedder: Embedder,
        query_handler: QueryHandler,
        web_searcher: WebSearcher,
        tx_factory: DBTransactionFactory,
        document_chunk_repo: DocumentChunkRepositoryInterface,
    ) -> None:
        """
        Initializes the RAGChatbot with its components.

        :param document_processor: The document processor instance.
        :param embedder: The embedder instance.
        :param query_handler: The query handler instance.
        :param web_searcher: The web searcher instance.
        """
        self.document_processor = document_processor
        self.embedder = embedder
        self.query_handler = query_handler
        self.web_searcher = web_searcher
        self._tx_factory = tx_factory
        self.document_chunk_repo = document_chunk_repo
        self._logger = BaseLogger(__name__)

    # ========================== QUERY METHODS ==========================

    async def process_query(
        self, query: str, chat_session_id: UUID, web_search_enabled: bool = False
    ) -> ChatbotResponse:
        """
        Processes a user query by searching the vector store and optionally
        performing a web search if no relevant results are found.
        """

        is_web_enabled = settings.web.IS_WEB_SEARCH_ENABLED and web_search_enabled

        results, sources = await self.query_handler.search_for_vector(
            query, chat_session_id
        )

        include_web_search = " or through web search" if is_web_enabled else ""

        # Default response object (AT THE START)
        response_data = ChatbotResponse(
            answer=(
                "I couldn't find relevant information to answer your "
                f"question in the uploaded documents{include_web_search}. Please "
                "try rephrasing your question or ask about a different "
                "topic."
            ),
            sources=[],
        )

        self._logger.debug(
            f"Search returned {len(results) if results else 0} results for "
            f"the query '{query}'."
        )

        # If no results are found and web search is not enabled, return the default response.
        if len(results) == 0 and not is_web_enabled:
            return response_data
        elif len(results) == 0:
            return response_data  # If web search is enabled, we will handle it below.

        response: PossibleResponse = self.query_handler.generate_responses(
            query=query, retrieved_chunks=results
        )

        if response is None or response == "OUT_OF_SCOPE":
            self._logger.info(
                f"No relevant information found for the query: '{query}'."
            )
            return response_data

        # Only perform if web search is indicated by the LLM and when web search fallback is enabled in the user request
        if response == "NEED_WEB_SEARCH" and web_search_enabled:
            self._logger.info(
                f"LLM indicated a need for web search for the query: '{query}'."
            )

            async with self._tx_factory.create() as tx:
                await self.web_searcher.search_and_ingest_web_content(
                    query=query, chat_session_id=chat_session_id, tx=tx
                )

            web_results, web_sources = await self.query_handler.search_for_vector(
                query, chat_session_id
            )

            if len(web_results) == 0:
                return response_data

            web_response: PossibleResponse = self.query_handler.generate_responses(
                query=query, retrieved_chunks=web_results, from_web_search=True
            )

            if web_response is None or web_response == "OUT_OF_SCOPE":
                self._logger.info(
                    f"No relevant information found from web search for the query: '{query}'."
                )
                return response_data

            if web_response == "NEED_WEB_SEARCH":
                return response_data  # Only return the default response if web search is needed again.

            # If we have a valid response from the web search, return it.
            self._logger.info(
                f"Generated response from web search for the query: '{query}'."
            )
            response_data.answer = web_response
            response_data.sources = web_sources
            return response_data

        # If we have a valid response from the initial search, return it.
        response_data.answer = response
        response_data.sources = sources

        self._logger.info(f"Generated response for query: '{query}'.")
        return response_data
