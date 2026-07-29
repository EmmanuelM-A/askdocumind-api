"""
Factory method to create and return an instance of RAGChatbot.
"""

from typing import Optional

from src.components.chatbot.core import RAGChatbot
from src.components.chatbot.query_handler import QueryHandler
from src.components.ingestion.document_processor import (
    DocumentProcessor,
    get_chunking_config,
)
from docling.document_converter import DocumentConverter
from src.components.retrieval.embedder import Embedder
from src.components.retrieval.reranker import CrossEncoderReranker
from src.components.retrieval.web_searcher import WebSearcher
from src.database.repository import get_database_repository
from src.database.repository.database_repository_factory import get_tx_factory

# Singleton instance of RAGChatbot (USE FACTORY METHOD TO ACCESS)
_rag_chatbot_instance: Optional[RAGChatbot] = None


def _build_chatbot() -> RAGChatbot:
    """Construct a fully wired RAGChatbot instance lazily."""
    embedder: Embedder = Embedder()
    query_handler: QueryHandler = QueryHandler(
        embedder=embedder,
        document_chunk_repo=get_database_repository("DOCUMENT_CHUNK"),
        reranker=CrossEncoderReranker(),
    )

    document_processor: DocumentProcessor = DocumentProcessor(
        converter=DocumentConverter(),
        config=get_chunking_config(),
        embedder=embedder,
        document_chunk_repository=get_database_repository("DOCUMENT_CHUNK"),
    )

    web_searcher: WebSearcher = WebSearcher(
        document_processor=document_processor,
        document_repository=get_database_repository("DOCUMENT"),
    )

    return RAGChatbot(
        query_handler=query_handler,
        document_processor=document_processor,
        web_searcher=web_searcher,
        tx_factory=get_tx_factory(),
    )


def get_chatbot() -> RAGChatbot:
    """Factory method to get a singleton instance of RAGChatbot."""

    global _rag_chatbot_instance

    if _rag_chatbot_instance is None:
        _rag_chatbot_instance = _build_chatbot()

    return _rag_chatbot_instance
