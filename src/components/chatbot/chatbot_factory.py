"""
Factory method to create and return an instance of RAGChatbot.
"""

from typing import Optional

from src.components.chatbot.core import RAGChatbot
from src.components.chatbot.query_handler import QueryHandler
from src.components.ingestion.processor_factory import (
    get_vector_processor,
    get_upload_document_processor,
)
from src.components.retrieval.embedder import Embedder
from src.components.retrieval.web_searcher import WebSearcher
from src.database.repository import get_database_repository
from src.database.repository.database_repository_factory import get_tx_factory

# Singleton instance of RAGChatbot (USE FACTORY METHOD TO ACCESS)
_rag_chatbot_instance: Optional[RAGChatbot] = None


def _build_chatbot() -> RAGChatbot:
    """Construct a fully wired RAGChatbot instance lazily."""
    embedder: Embedder = Embedder()
    query_handler: QueryHandler = QueryHandler(
        embedder=embedder, document_chunk_repo=get_database_repository("DOCUMENT_CHUNK")
    )
    web_searcher: WebSearcher = WebSearcher(
        embedder=embedder,
        vector_processor=get_vector_processor(),
    )

    return RAGChatbot(
        document_processor=get_upload_document_processor(),
        embedder=embedder,
        query_handler=query_handler,
        web_searcher=web_searcher,
        tx_factory=get_tx_factory(),
        document_chunk_repo=get_database_repository("DOCUMENT_CHUNK"),
    )


def get_chatbot() -> RAGChatbot:
    """Factory method to get a singleton instance of RAGChatbot."""

    global _rag_chatbot_instance

    if _rag_chatbot_instance is None:
        _rag_chatbot_instance = _build_chatbot()

    return _rag_chatbot_instance
