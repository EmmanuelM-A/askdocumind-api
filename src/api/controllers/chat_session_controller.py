"""
Controller layer responsible for managing chat sessions.
Handles application logic related to chat sessions and interactions with the
service layer.
"""

from typing import Optional
from uuid import UUID

from fastapi import status
from fastapi import Request
from starlette.responses import JSONResponse

from src.api.services.chats.chat_sessions import ChatSessionService
from src.api.services.service_factory import get_chat_service
from src.api.services.validation.chat_session import (
    CreateChatSessionSchema,
    DeleteChatSessionSchema,
    GetChatSessionMessagesSchema,
    GetChatSessionSchema,
    InitializeChatSessionSchema,
)
from src.api.utils.api_responses import SuccessResponseModel
from src.api.utils.response_delivery import create_success_response
from src.database.repository.interfaces import ChatMessageSearchCriteria
from src.config.configs import settings
from src.logger.base_logger import BaseLogger


class ChatSessionController:
    """
    Orchestrates chat session requests between API and service layers.
    """

    def __init__(self):
        self._chat_service: Optional[ChatSessionService] = None
        self._logger = BaseLogger(__name__)

    def lazy_init(self) -> None:
        """Lazy initialize service dependency."""
        if self._chat_service is None:
            self._chat_service = get_chat_service()

    async def create_chat_session_endpoint(
        self, input: CreateChatSessionSchema
    ) -> JSONResponse:
        self.lazy_init()
        assert self._chat_service is not None

        created_id = await self._chat_service.create_new_chat(input)

        response_model = SuccessResponseModel(
            message="Chat session created successfully.",
            data={"chat_id": str(created_id)},
        )

        return create_success_response(
            status_code=status.HTTP_201_CREATED,
            success_response_model=response_model,
        )

    async def init_chat_session_endpoint(
        self, input: InitializeChatSessionSchema
    ) -> JSONResponse:
        """Initialize or retrieve a chat session for a user."""
        self.lazy_init()
        assert self._chat_service is not None

        chat_id = await self._chat_service.init_chat_session(input)

        response_model = SuccessResponseModel(
            message="Chat session initialized successfully.",
            data={"chat_id": str(chat_id)},
        )

        return create_success_response(
            status_code=status.HTTP_200_OK,
            success_response_model=response_model,
        )

    async def get_chat_session_endpoint(
        self, input: GetChatSessionSchema
    ) -> JSONResponse:
        self.lazy_init()
        assert self._chat_service is not None

        chat_metadata = await self._chat_service.get_chat_metadata(input)

        response_model = SuccessResponseModel(
            message="Chat session fetched successfully.",
            data=chat_metadata,
        )

        return create_success_response(
            status_code=status.HTTP_200_OK,
            success_response_model=response_model,
        )

    async def delete_chat_session_endpoint(self, input: DeleteChatSessionSchema) -> JSONResponse:
        self.lazy_init()
        assert self._chat_service is not None

        deleted_id = await self._chat_service.delete_chat(input)

        response_model = SuccessResponseModel(
            message="Chat session deleted successfully.",
            data={"chat_id": str(deleted_id)},
        )
        return create_success_response(
            status_code=status.HTTP_200_OK,
            success_response_model=response_model,
        )

    async def get_chat_messages_endpoint(self, input: GetChatSessionMessagesSchema) -> JSONResponse:
        self.lazy_init()
        assert self._chat_service is not None

        criteria = ChatMessageSearchCriteria(session_id=input.chat_id)
        messages = await self._chat_service.get_chat_messages(data=input, criteria=criteria)

        response_model = SuccessResponseModel(
            message="Chat messages fetched successfully.",
            data=messages,
        )
        return create_success_response(
            status_code=status.HTTP_200_OK,
            success_response_model=response_model,
        )
