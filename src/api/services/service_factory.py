"""Factory helpers for lazily constructing service singletons."""

from typing import TYPE_CHECKING

from src.api.services.chat_sessions import ChatSessionService
from src.components.chatbot.chatbot_factory import get_chatbot
from src.components.ingestion.processor_factory import get_vector_processor
from src.database.repository import get_database_repository
from src.database.repository.database_repository_factory import get_tx_factory
from src.database.storage import get_storage_service

if TYPE_CHECKING:
    from src.api.services.auth.anonymous_user import AnonymousUserSessionService
    from src.api.services.documents.document_uploads import UploadService
    from src.api.services.rag_chatbot import RAGChatbotService

_rag_chatbot_service: "RAGChatbotService | None" = None
_upload_service: "UploadService | None" = None
_chat_service: "ChatSessionService | None" = None
_anonymous_user_service: "AnonymousUserSessionService | None" = None


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
        from src.api.services.documents.document_uploads import UploadService

        _upload_service = UploadService(
            storage_service=get_storage_service(),
            document_repo=get_database_repository("DOCUMENT"),
            chat_session_repo=get_database_repository("CHAT_SESSION"),
            vector_processor=get_vector_processor(),
            tx_factory=get_tx_factory(),
        )

    return _upload_service


def get_chat_service() -> "ChatSessionService":
    """Return a singleton instance of the chat session service."""
    global _chat_service

    if _chat_service is None:
        from src.api.services.chat_sessions import ChatSessionService

        _chat_service = ChatSessionService(
            storage=get_storage_service(),
            chat_session_repo=get_database_repository("CHAT_SESSION"),
            chat_message_repo=get_database_repository("CHAT_MESSAGE"),
            tx_factory=get_tx_factory(),
        )

    return _chat_service


def get_anonymous_user_service() -> "AnonymousUserSessionService":
    """Return a singleton instance of the anonymous user session service."""
    global _anonymous_user_service

    if _anonymous_user_service is None:
        from src.api.services.auth.anonymous_user import AnonymousUserSessionService

        _anonymous_user_service = AnonymousUserSessionService(
            user_repo=get_database_repository("USER")
        )

    return _anonymous_user_service
