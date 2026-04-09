"""
Routes for the Chat Session endpoints.
Provides API routes for interacting with the Chat Session.
"""

from uuid import UUID

from fastapi import APIRouter
from fastapi import Request

from src.api.controllers.chat_session_controller import ChatSessionController
from src.api.services.validation.schemas import CreateChatSchema, UpdateChatMetadataSchema

chat_session_router = APIRouter(prefix="/sessions", tags=["Chat Session"])

_controller = ChatSessionController()


# @chat_session_router.get("/", summary="Get all chat sessions")
# async def get_chat_sessions():
#     pass


@chat_session_router.post("", summary="Create chat session")
@chat_session_router.post("/", include_in_schema=False)
async def create_chat_session(http_request: Request, request: CreateChatSchema):
    return await _controller.create_chat_session_endpoint(http_request, request)


@chat_session_router.get("/{session_id}", summary="Get chat session by ID")
async def get_chat_session(session_id: UUID):
    return await _controller.get_chat_session_endpoint(session_id)


@chat_session_router.patch("/{session_id}", summary="Update chat session")
async def update_chat_session(session_id: UUID, request: UpdateChatMetadataSchema):
    return await _controller.update_chat_session_endpoint(session_id, request)


@chat_session_router.delete("/{session_id}", summary="Delete chat session")
async def delete_chat_session(session_id: UUID):
    return await _controller.delete_chat_session_endpoint(session_id)


@chat_session_router.get(
    "/{session_id}/messages", summary="Get chat messages for a session"
)
async def get_chat_messages(session_id: UUID):
    return await _controller.get_chat_messages_endpoint(session_id)
