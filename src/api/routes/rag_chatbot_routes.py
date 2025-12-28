"""
Routes for the RAG Chatbot endpoints.
Provides API routes for interacting with the RAG Chatbot.
"""

from fastapi import APIRouter

from src.api.controllers.rag_chatbot_controller import RAGChatbotController
from src.services.validation.rag_validation import ChatRequest

rag_chatbot_router = APIRouter(prefix="/chat", tags=["RAG Chatbot"])

_controller = RAGChatbotController()


@rag_chatbot_router.post("/", summary="RAG Chatbot Interaction")
async def chat(request: ChatRequest):
    """Endpoint to handle chat requests."""

    return await _controller.chat_endpoint(request)
