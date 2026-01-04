"""
Routes for the Chat Session endpoints.
Provides API routes for interacting with the Chat Session.
"""

from fastapi import APIRouter

from src.api.controllers.chat_session_controller import ChatSessionController

chat_session_router = APIRouter(prefix="/sessions", tags=["Chat Session"])

_controller = ChatSessionController()


@chat_session_router.get("/", summary="Get all chat sessions")
async def get_chat_sessions():
    pass


@chat_session_router.post("/", summary="Create chat session")
async def create_chat_session():
    pass


@chat_session_router.get("/{session_id}", summary="Get chat session by ID")
async def get_chat_session():
    pass


@chat_session_router.delete("/{session_id}", summary="Update chat session by ID")
async def delete_chat_session():
    pass


@chat_session_router.get(
    "/{session_id}/messages", summary="Get chat messages for a session"
)
async def get_chat_messages():
    pass
