"""
Service module for handling RAG chatbot interactions.
"""

from src.components.chatbot.chatbot_factory import get_chatbot
from src.config.constants import ChatMessageRole
from src.database.models import ChatSession, ChatMessage
from src.database.repository.database_repository_factory import get_database_repository
from src.services.validation.rag_validation import ChatRequest, check_if_chat_exists
from src.utils.api_responses import SuccessResponseModel


class ChatbotService:
    """Service class for RAG chatbot interactions."""

    def __init__(self):
        self.chat_session_repo = get_database_repository(ChatSession)
        self.chat_message_repo = get_database_repository(ChatMessage)
        self.chatbot = get_chatbot()

    async def handle_chat(self, request: ChatRequest) -> SuccessResponseModel:
        """Handles a chat request."""

        await check_if_chat_exists(
            chat_id=request.chat_id,
            chat_session_repo=self.chat_session_repo,
            chatbot=self.chatbot,
        )

        response = self.chatbot.process_query(
            sanitized_query=request.user_query,
            index_id=str(request.chat_id),
            web_search_enabled=request.web_search_enabled,
        )

        user_query_chat_message = ChatMessage(
            session_id=request.chat_id,
            role=ChatMessageRole.USER,
            content=request.user_query,
        )

        assistant_response_chat_message = ChatMessage(
            session_id=request.chat_id,
            role=ChatMessageRole.ASSISTANT,
            content=response["answer"],
        )

        await self.chat_message_repo.create_many(
            [
                user_query_chat_message,
                assistant_response_chat_message,
            ]
        )

        return SuccessResponseModel(
            message="The chat query was processed successfully.",
            data=response,
        )
