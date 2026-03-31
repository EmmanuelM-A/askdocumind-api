"""
Controller layer responsible for managing chat sessions.
Handles application logic related to chat sessions and interactions with the
service layer.
"""

from uuid import UUID

from fastapi import status
from starlette.responses import JSONResponse

from src.api.services.service_factory import get_chat_service
from src.api.services.validation.schemas import CreateChatSchema, UpdateChatMetadataSchema
from src.api.utils.api_responses import SuccessResponseModel
from src.api.utils.response_delivery import create_success_response
from src.database.repository.interfaces import ChatMessageSearchCriteria


class ChatSessionController:
    """
    Orchestrates chat session requests between API and service layers.
    """

    def __init__(self):
        self.chat_service = None

    def lazy_init(self) -> None:
        """Lazy initialize service dependency."""
        if self.chat_service is None:
            self.chat_service = get_chat_service()

    async def create_chat_session_endpoint(
        self, request: CreateChatSchema
    ) -> JSONResponse:
        self.lazy_init()

        created_id = await self.chat_service.create_new_chat(request)
        response_model = SuccessResponseModel(
            message="Chat session created successfully.",
            data={"chat_id": str(created_id)},
        )
        return create_success_response(
            status_code=status.HTTP_201_CREATED,
            success_response_model=response_model,
        )

    async def get_chat_session_endpoint(self, session_id: UUID) -> JSONResponse:
        self.lazy_init()

        chat = await self.chat_service.get_chat_metadata(session_id)
        response_model = SuccessResponseModel(
            message="Chat session fetched successfully.",
            data=chat.to_dict(),
        )
        return create_success_response(
            status_code=status.HTTP_200_OK,
            success_response_model=response_model,
        )

    async def update_chat_session_endpoint(
        self, session_id: UUID, request: UpdateChatMetadataSchema
    ) -> JSONResponse:
        self.lazy_init()

        updated_chat = await self.chat_service.update_chat_metadata(
            chat_id=session_id,
            data=request,
        )
        response_model = SuccessResponseModel(
            message="Chat session updated successfully.",
            data=updated_chat.to_dict(),
        )
        return create_success_response(
            status_code=status.HTTP_200_OK,
            success_response_model=response_model,
        )

    async def delete_chat_session_endpoint(self, session_id: UUID) -> JSONResponse:
        self.lazy_init()

        deleted_id = await self.chat_service.delete_chat(session_id)
        response_model = SuccessResponseModel(
            message="Chat session deleted successfully.",
            data={"chat_id": str(deleted_id)},
        )
        return create_success_response(
            status_code=status.HTTP_200_OK,
            success_response_model=response_model,
        )

    async def get_chat_messages_endpoint(self, session_id: UUID) -> JSONResponse:
        self.lazy_init()

        criteria = ChatMessageSearchCriteria(session_id=session_id)
        messages = await self.chat_service.get_chat_messages(criteria)

        response_model = SuccessResponseModel(
            message="Chat messages fetched successfully.",
            data=[message.to_dict() for message in messages],
        )
        return create_success_response(
            status_code=status.HTTP_200_OK,
            success_response_model=response_model,
        )
