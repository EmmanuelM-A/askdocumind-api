"""
Routes for the RAG Chatbot endpoints.
Provides API routes for interacting with the RAG Chatbot.
"""

from fastapi import APIRouter, Request

from src.api.controllers.rag_chatbot_controller import RAGChatbotController
from src.api.middleware.rate_limiter import (
    chat_query_limit,
    user_key_func,
    limiter,
)
from src.api.services.validation.rag_validation import ChatRequest

rag_chatbot_router = APIRouter(prefix="/chat", tags=["RAG Chatbot"])

_controller = RAGChatbotController()


@rag_chatbot_router.post("/", summary="RAG Chatbot Interaction")
@limiter.limit(chat_query_limit, key_func=user_key_func)
async def chat(_request: Request, chat_request: ChatRequest):
    """Endpoint to handle chat requests."""

    return await _controller.chat_endpoint(chat_request)
