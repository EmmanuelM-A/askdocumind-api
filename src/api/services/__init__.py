from src.api.services.rag_chatbot import ChatbotService
from src.components.chatbot.chatbot_factory import get_chatbot
from src.database.models import ChatSession, ChatMessage
from src.database.repository import get_database_repository

chatbot_service = ChatbotService(
    get_database_repository(ChatSession),
    get_database_repository(ChatMessage),
    get_chatbot(),
)
