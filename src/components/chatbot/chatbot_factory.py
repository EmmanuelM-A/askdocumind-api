"""
Factory method to create and return an instance of RAGChatbot.
"""

from typing import Optional

from src.components.chatbot.core import RAGChatbot
from src.components.chatbot.query_handler import QueryHandler
from src.components.ingestion.document_processor import DocumentProcessor
from src.components.retrieval.embedder import Embedder
from src.components.retrieval.faiss_store import FaissVectorStore
from src.components.retrieval.vector_store import VectorStore
from src.components.retrieval.web_searcher import WebSearcher

# Singleton instance of RAGChatbot (USE FACTORY METHOD TO ACCESS)
_rag_chatbot_instance: Optional[RAGChatbot] = None


def _build_chatbot() -> RAGChatbot:
    """Construct a fully wired RAGChatbot instance lazily."""
    document_processor: DocumentProcessor = DocumentProcessor()
    vector_store: VectorStore = FaissVectorStore()
    embedder: Embedder = Embedder()
    query_handler: QueryHandler = QueryHandler(embedder=embedder)
    web_searcher: WebSearcher = WebSearcher(
        embedder=embedder,
        document_processor=document_processor,
        vector_store=vector_store,
    )

    return RAGChatbot(
        vector_store=vector_store,
        document_processor=document_processor,
        embedder=embedder,
        query_handler=query_handler,
        web_searcher=web_searcher,
    )


def get_chatbot() -> RAGChatbot:
    """Factory method to get a singleton instance of RAGChatbot."""

    global _rag_chatbot_instance

    if _rag_chatbot_instance is None:
        _rag_chatbot_instance = _build_chatbot()

    return _rag_chatbot_instance
