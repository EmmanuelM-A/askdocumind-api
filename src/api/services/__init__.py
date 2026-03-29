from src.api.services.document_uploads import UploadService
from src.api.services.rag_chatbot import RAGChatbotService
from src.components.chatbot.chatbot_factory import get_chatbot
from src.database.repository import get_database_repository
from src.database.storage import get_storage_service

rag_chatbot_service = RAGChatbotService(
    get_database_repository("CHAT_SESSION"),
    get_database_repository("CHAT_MESSAGE"),
    get_chatbot(),
)

upload_service = UploadService(
    get_storage_service(),
    get_database_repository("CHAT_SESSION"),
    get_database_repository("DOCUMENT"),
    get_chatbot(),
)

__all__ = ["rag_chatbot_service", "upload_service"]
