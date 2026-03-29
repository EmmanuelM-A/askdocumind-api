"""Factory helpers for lazily constructing service singletons."""

from typing import TYPE_CHECKING

from src.components.chatbot.chatbot_factory import get_chatbot
from src.database.repository import get_database_repository
from src.database.storage import get_storage_service

if TYPE_CHECKING:
    from src.api.services.document_uploads import UploadService
    from src.api.services.rag_chatbot import RAGChatbotService

_rag_chatbot_service: "RAGChatbotService | None" = None
_upload_service: "UploadService | None" = None


def get_rag_chatbot_service() -> "RAGChatbotService":
    """Return a singleton instance of the RAG chatbot service."""
    global _rag_chatbot_service

    if _rag_chatbot_service is None:
        from src.api.services.rag_chatbot import RAGChatbotService

        _rag_chatbot_service = RAGChatbotService(
            get_database_repository("CHAT_SESSION"),
            get_database_repository("CHAT_MESSAGE"),
            get_chatbot(),
        )

    return _rag_chatbot_service


def get_upload_service() -> "UploadService":
    """Return a singleton instance of the upload service."""
    global _upload_service

    if _upload_service is None:
        from src.api.services.document_uploads import UploadService

        _upload_service = UploadService(
            get_storage_service(),
            get_database_repository("CHAT_SESSION"),
            get_database_repository("DOCUMENT"),
            get_chatbot(),
        )

    return _upload_service

