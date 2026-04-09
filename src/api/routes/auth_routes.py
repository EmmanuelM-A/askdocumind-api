"""
Routes for the Chat Session endpoints.
Provides API routes for interacting with the Chat Session.
"""

from uuid import UUID

from fastapi import APIRouter

from src.api.controllers.auth_controller import AuthController
from src.api.controllers.chat_session_controller import ChatSessionController
from src.api.services.validation.schemas import (
    CreateChatSchema,
    UpdateChatMetadataSchema,
)

auth_router = APIRouter(prefix="/auth", tags=["Chat Session"])

_controller = AuthController()


@auth_router.post("/anonymous/", summary="Create an anonymous user session")
async def create_chat_session(request: CreateChatSchema):
    return await _controller.create_chat_session_endpoint(request)


@auth_router.get("/{session_id}", summary="Get chat session by ID")
async def get_chat_session(session_id: UUID):
    return await _controller.get_chat_session_endpoint(session_id)
