"""
Controller layer fot the RAG chatbot interactions.
"""

from typing import Optional

from fastapi import status
from starlette.responses import JSONResponse

from src.api.services.chatbot.rag_chatbot import RAGChatbotService
from src.api.services.service_factory import get_rag_chatbot_service
from src.api.services.validation.chatbot import ChatRequest
from src.api.utils.api_responses import SuccessResponseModel
from src.api.utils.response_delivery import create_success_response


class RAGChatbotController:
    """
    Orchestrates RAG chatbot requests between API and service layers
    """

    def __init__(self):
        self._rag_chatbot_service: Optional[RAGChatbotService] = None
    
    def _lazy_init(self) -> None:
        """Lazy initialize variables."""
        if self._rag_chatbot_service is None:
            self._rag_chatbot_service = get_rag_chatbot_service()

    async def chat_endpoint(self, input: ChatRequest) -> JSONResponse:
        """
        Processes a chat request and returns the chatbot's response.
        """
        self._lazy_init()
        assert self._rag_chatbot_service is not None

        response = await self._rag_chatbot_service.handle_chat_request(input)
        
        response_model = SuccessResponseModel(
            message="Chatbot response generated successfully.",
            data=response
        )

        return create_success_response(
            status_code=status.HTTP_200_OK, success_response_model=response_model
        )
