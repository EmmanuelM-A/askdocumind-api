"""
Service module for handling RAG chatbot interactions.
"""

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.components.chatbot.chatbot_factory import get_chatbot
from src.config.constants import ChatMessageRole
from src.database.models import ChatSession, ChatMessage
from src.database.repository.database_repository_factory import get_database_repository
from src.errors.custom_exceptions import throw_not_found_error, throw_server_error
from src.services.validation.rag_validation import ChatRequest
from src.utils.api_responses import SuccessResponseModel


class ChatbotService:
    def __init__(self):
        self.chat_session_repo = get_database_repository(ChatSession)
        self.chat_message_repo = get_database_repository(ChatMessage)
        self.chatbot = get_chatbot()

    def handle_chat(self, request: ChatRequest) -> SuccessResponseModel:
        """Handles a chat request."""

        if not self.chat_session_repo.exists(
            str(request.chat_id)
        ):  # TODO CHANGE str ids to UUID
            throw_not_found_error(
                message=f"Chat session with ID {request.chat_id} not found.",
                error_code="CHAT_SESSION_NOT_FOUND",
            )

        if not self.chatbot.chat_exists(index_chat_id=request.chat_id):
            throw_not_found_error(
                message=f"Chat with ID {request.chat_id} not found in vector store.",
                error_code="CHAT_NOT_FOUND_IN_VECTOR_STORE",
            )

        response = self.chatbot.process_query(
            query=request.user_query,
            index_id=request.chat_id,
            web_search_enabled=request.web_search_enabled,
        )

        user_query_chat_message = ChatMessage(
            session_id=request.chat_id,
            role=ChatMessageRole.USER,
            content=request.user_query,  # GET SANITIZED QUERY
        )

        assistant_response_chat_message = ChatMessage(
            session_id=request.chat_id,
            role=ChatMessageRole.ASSISTANT,
            content=response["answer"],
        )

        try:  # TODO: TRANSACTION MANAGEMENT + ASYNC + BULK INSERT
            self.chat_message_repo.create(user_query_chat_message)
            self.chat_message_repo.create(assistant_response_chat_message)
        except (IntegrityError, SQLAlchemyError, Exception) as e:
            throw_server_error(
                message="Failed to store chat messages in the database.",
                error_code="CHAT_MESSAGE_STORAGE_FAILED",
                stack_trace=str(e),
            )

        return SuccessResponseModel(
            message="The chat query was processed successfully.",
            data=response,
        )
