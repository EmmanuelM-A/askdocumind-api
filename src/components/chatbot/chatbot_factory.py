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

# RAG Chatbot component instances
_document_processor: DocumentProcessor = DocumentProcessor()
_vector_store: VectorStore = FaissVectorStore()
_embedder: Embedder = Embedder()
_query_handler: QueryHandler = QueryHandler(embedder=_embedder)
_web_searcher: WebSearcher = WebSearcher(
    embedder=_embedder,
    document_processor=_document_processor,
    vector_store=_vector_store,
)

# Singleton instance of RAGChatbot (USE FACTORY METHOD TO ACCESS)
_rag_chatbot_instance: Optional[RAGChatbot] = None


def get_chatbot() -> RAGChatbot:
    """Factory method to get a singleton instance of RAGChatbot."""

    global _rag_chatbot_instance

    if _rag_chatbot_instance is None:
        _rag_chatbot_instance = RAGChatbot(
            vector_store=_vector_store,
            document_processor=_document_processor,
            embedder=_embedder,
            query_handler=_query_handler,
            web_searcher=_web_searcher,
        )

    return _rag_chatbot_instance
