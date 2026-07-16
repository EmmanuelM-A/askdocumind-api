"""Factory helpers for lazily constructing service singletons."""

from typing import TYPE_CHECKING

from src.api.services.chats.chat_sessions import ChatSessionService
from src.api.utils.session_manager import get_token_manager
from src.components.chatbot.chatbot_factory import get_chatbot
from src.components.ingestion.document_processor import DocumentProcessor, get_chunking_config
from src.components.retrieval.embedder import Embedder
from src.database.repository import get_database_repository
from docling.document_converter import DocumentConverter

from src.database.repository.database_repository_factory import get_tx_factory

if TYPE_CHECKING:
    from src.api.services.auth.anonymous_user import AnonymousUserSessionService
    from src.api.services.documents.document_uploads import UploadDocumentService
    from src.api.services.documents.document_cleanup import DocumentCleanupService
    from src.api.services.chatbot.rag_chatbot import RAGChatbotService

_rag_chatbot_service: "RAGChatbotService | None" = None
_upload_service: "UploadDocumentService | None" = None
_chat_service: "ChatSessionService | None" = None
_anonymous_user_service: "AnonymousUserSessionService | None" = None
_document_cleanup_service: "DocumentCleanupService | None" = None


def get_rag_chatbot_service() -> "RAGChatbotService":
    """Return a singleton instance of the RAG chatbot service."""
    global _rag_chatbot_service

    if _rag_chatbot_service is None:
        from src.api.services.chatbot.rag_chatbot import RAGChatbotService

        _rag_chatbot_service = RAGChatbotService(
            get_database_repository("CHAT_SESSION"),
            get_database_repository("CHAT_MESSAGE"),
            get_chatbot(),
        )

    return _rag_chatbot_service


def get_upload_service() -> "UploadDocumentService":
    """Return a singleton instance of the upload service."""
    global _upload_service

    if _upload_service is None:
        from src.api.services.documents.document_uploads import UploadDocumentService

        _upload_service = UploadDocumentService(
            document_repo=get_database_repository("DOCUMENT"),
            chat_session_repo=get_database_repository("CHAT_SESSION"),
            document_processor=DocumentProcessor(
                converter=DocumentConverter(),
                config=get_chunking_config(),
                embedder=Embedder(),
                document_chunk_repository=get_database_repository("DOCUMENT_CHUNK"),
            ),
            tx_factory=get_tx_factory(),
        )

    return _upload_service


def get_chat_service() -> "ChatSessionService":
    """Return a singleton instance of the chat session service."""
    global _chat_service

    if _chat_service is None:
        from src.api.services.chats.chat_sessions import ChatSessionService

        _chat_service = ChatSessionService(
            chat_session_repo=get_database_repository("CHAT_SESSION"),
            chat_message_repo=get_database_repository("CHAT_MESSAGE"),
        )

    return _chat_service


def get_anonymous_user_service() -> "AnonymousUserSessionService":
    """Return a singleton instance of the anonymous user session service."""
    global _anonymous_user_service

    if _anonymous_user_service is None:
        from src.api.services.auth.anonymous_user import AnonymousUserSessionService

        _anonymous_user_service = AnonymousUserSessionService(
            user_repo=get_database_repository("USER"), # type: ignore
            token_manager=get_token_manager(),
        )

    return _anonymous_user_service


def get_document_cleanup_service() -> "DocumentCleanupService":
    """Return a singleton instance of the document cleanup service."""
    global _document_cleanup_service

    if _document_cleanup_service is None:
        from src.api.services.documents.document_cleanup import DocumentCleanupService

        _document_cleanup_service = DocumentCleanupService(
            document_repo=get_database_repository("DOCUMENT"),  # type: ignore
            chunk_repo=get_database_repository("DOCUMENT_CHUNK"),  # type: ignore
        )

    return _document_cleanup_service
