"""
Service module for handling RAG chatbot interactions.
"""

from src.components.chatbot.core import RAGChatbot, ChatbotResponse
from src.config.constants import ChatMessageRole
from src.database.models import ChatMessage
from src.api.services.validation.rag_validation import ChatRequest, check_if_chat_exists
from src.api.utils.api_responses import SuccessResponseModel
from src.database.repository.interfaces import (
    ChatSessionRepositoryInterface,
    ChatMessageRepositoryInterface,
)
from src.logger.base_logger import BaseLogger


class RAGChatbotService:
    """Service class for RAG chatbot interactions."""

    def __init__(
        self,
        chat_session_repo: ChatSessionRepositoryInterface,
        chat_message_repo: ChatMessageRepositoryInterface,
        chatbot: RAGChatbot,
    ) -> None:
        self.chat_session_repo = chat_session_repo
        self.chat_message_repo = chat_message_repo
        self.chatbot = chatbot
        self._logger = BaseLogger(__name__)

    async def handle_chat_request(self, request: ChatRequest) -> SuccessResponseModel:
        """Handles a chat request."""

        await check_if_chat_exists(
            chat_id=request.chat_id, chat_session_repo=self.chat_session_repo
        )

        self._logger.debug("Received chat request and chat session validated")

        response: ChatbotResponse = await self.chatbot.process_query(
            query=request.user_query,
            chat_session_id=request.chat_id,
            web_search_enabled=request.web_search_enabled,
        )

        self._logger.debug("Chatbot processed the query and generated a response")

        user_query_chat_message = ChatMessage(
            session_id=request.chat_id,
            role=ChatMessageRole.USER,
            content=request.user_query,
        )

        assistant_response_chat_message = ChatMessage(
            session_id=request.chat_id,
            role=ChatMessageRole.ASSISTANT,
            content=response.answer,
        )

        await self.chat_message_repo.create_many(
            [
                user_query_chat_message,
                assistant_response_chat_message,
            ]
        )

        self._logger.info("Chatbot query and response have been saved")

        return SuccessResponseModel(
            message="The chat query was processed successfully.",
            data=response.to_dict(),
        )
