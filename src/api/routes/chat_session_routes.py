"""
Routes for the Chat Session endpoints.
Provides API routes for interacting with the Chat Session.
"""

from uuid import UUID

from fastapi import APIRouter, Request

from src.api.controllers.chat_session_controller import ChatSessionController
from src.api.services.validation.chat_session import CreateChatSessionData

chat_session_router = APIRouter(prefix="/sessions", tags=["Chat Session"])

_controller = ChatSessionController()


@chat_session_router.post("/", summary="Create chat session")
async def create_chat_session(request: Request, input: CreateChatSessionData):
    return await _controller.create_chat_session_endpoint(request, input)


@chat_session_router.post("/init", summary="Initialize or retrieve chat session")
async def init_chat_session(request: Request, input: CreateChatSessionData):
    return await _controller.init_chat_session_endpoint(request, input)


@chat_session_router.get("/{session_id}", summary="Get chat session by ID")
async def get_chat_session(request: Request, session_id: UUID):
    return await _controller.get_chat_session_endpoint(request, session_id)


@chat_session_router.delete("/{session_id}", summary="Delete chat session")
async def delete_chat_session(request: Request, session_id: UUID):
    return await _controller.delete_chat_session_endpoint(request, session_id)


@chat_session_router.get(
    "/{session_id}/messages", summary="Get chat messages for a session"
)
async def get_chat_messages(request: Request, session_id: UUID):
    return await _controller.get_chat_messages_endpoint(request, session_id)
