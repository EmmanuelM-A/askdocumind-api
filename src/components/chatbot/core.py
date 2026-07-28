"""
Handles chatbot interactions using Retrieval-Augmented Generation (RAG).
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List
from uuid import UUID

from src.components.chatbot.query_handler import PossibleResponse, QueryHandler
from src.components.ingestion.document_processor import DocumentProcessor
from src.components.prompts.prompt_loader import create_prompt_template
from src.components.retrieval.query_expander import expand_query
from src.components.retrieval.web_searcher import WebSearcher
from src.config.configs import settings
from src.database.repository.interfaces.db_transaction import DBTransactionFactory
from src.errors.api_exceptions import ApiException
from src.logger.base_logger import BaseLogger

# Per-session web search counter. Resets on server restart, which is acceptable
# for keeping Brave API usage within the free tier (2,000 req/month).
_web_search_counts: Dict[str, int] = defaultdict(int)


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
        query_handler: QueryHandler,
        document_processor: DocumentProcessor,
        web_searcher: WebSearcher,
        tx_factory: DBTransactionFactory,
    ) -> None:
        """
        Initializes the RAGChatbot with its components.

        :param document_processor: The document processor instance.
        :param embedder: The embedder instance.
        :param query_handler: The query handler instance.
        :param web_searcher: The web searcher instance.
        :param tx_factory: Used to open a transaction around web-search
            ingestion so it can be committed or rolled back depending on
            whether the ingested content actually produces a usable answer.
        """
        self._query_handler = query_handler
        self._document_processor = document_processor
        self._web_searcher = web_searcher
        self._tx_factory = tx_factory
        self._expansion_prompt_template = create_prompt_template(
            settings.llm.QUERY_EXPANSION_PROMPT_FILEPATH
        )
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

        try:
            expanded_query = expand_query(
                query=query, llm=self._query_handler.llm, prompt_template=self._expansion_prompt_template
            )
        except ApiException as e:
            self._logger.warning(
                f"Query expansion failed ({e.error.code}); falling back to the "
                f"original query: '{query}'."
            )
            expanded_query = query

        results, sources = await self._query_handler.search_for_vectors(
            expanded_query, chat_session_id
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

        # Always ask the LLM to judge the query, even with zero retrieved chunks -
        # this lets it classify OUT_OF_SCOPE (generic trivia) vs NEED_WEB_SEARCH
        # (plausibly document-related) instead of blindly falling back to web
        # search whenever local vector search finds nothing.
        response: PossibleResponse = self._query_handler.generate_response(
            query=expanded_query, retrieved_chunks=results
        )

        if response == "OUT_OF_SCOPE":
            response_data.answer = f"The query '{query}' is outside of the scope of the uploaded documents."
            return response_data

        if response is None:
            self._logger.info(f"No relevant information found for the query: '{query}'.")
            return response_data

        if response != "NEED_WEB_SEARCH":
            response_data.answer = response
            response_data.sources = sources
            self._logger.info(f"Generated response for query: '{query}'.")
            return response_data

        # LLM signalled NEED_WEB_SEARCH — fall through to web search below
        self._logger.info(f"LLM requested web search for query: '{query}'.")

        # Either no matching chunks at all, or the LLM explicitly asked for a
        # web search — proceed only if web search is enabled.
        if not is_web_enabled:
            return response_data

        session_key = str(chat_session_id)
        if _web_search_counts[session_key] >= settings.web.MAX_WEB_SEARCHES_PER_SESSION:
            self._logger.warning(
                f"Web search limit ({settings.web.MAX_WEB_SEARCHES_PER_SESSION}) "
                f"reached for session {chat_session_id}."
            )
            response_data.answer = (
                "Web search is no longer available for this session — the limit has been reached. "
                "Disable its usage! And try rephrasing your question based solely on your uploaded documents. "
            )
            return response_data

        _web_search_counts[session_key] += 1

        self._logger.info(
            f"Attempting web search for query: '{query}' "
            f"(search {_web_search_counts[session_key]}/{settings.web.MAX_WEB_SEARCHES_PER_SESSION} for session)."
        )

        # Web content is only worth persisting if it actually produces a usable answer
        tx = self._tx_factory.create()
        try:
            await tx.__aenter__()

            await self._web_searcher.ingest_web_content(
                query=expanded_query, chat_session_id=chat_session_id, tx=tx,
            )

            web_results, web_sources = await self._query_handler.search_for_vectors(
                expanded_query, chat_session_id, tx=tx
            )

            if len(web_results) == 0:
                self._logger.debug(
                    f"No relevant web results found for the query: '{query}'."
                )
                await tx.rollback()
                return response_data

            web_response: PossibleResponse = self._query_handler.generate_response(
                query=expanded_query, retrieved_chunks=web_results, from_web_search=True
            )

            if not web_response or web_response in ("OUT_OF_SCOPE", "NEED_WEB_SEARCH"):
                self._logger.info(
                    f"Web search did not produce a usable response for '{query}'; "
                    "discarding the ingested web content."
                )
                await tx.rollback()
                return response_data

            await tx.commit()
        finally:
            await tx.close()

        self._logger.info(f"Generated response from web search for the query: '{query}'.")
        response_data.answer = web_response
        response_data.sources = web_sources
        return response_data
