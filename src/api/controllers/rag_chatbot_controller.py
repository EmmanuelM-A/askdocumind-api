"""
Controller layer fot the RAG chatbot interactions.
"""

from fastapi import status
from starlette.responses import JSONResponse

from src.api.services import ChatbotService
from src.api.services.validation.rag_validation import ChatRequest
from src.api.utils.response_delivery import create_success_response


class RAGChatbotController:
    """
    Orchestrates RAG chatbot requests between API and service layers
    """

    def __init__(self):
        self.rag_chatbot_service = ChatbotService()

    async def chat_endpoint(self, request: ChatRequest) -> JSONResponse:
        """
        Processes a chat request and returns the chatbot's response.

        :param request: ChatRequest object containing user query and context.
        :return: JSONResponse with the chatbot's answer.
        """

        chat_response = await self.rag_chatbot_service.handle_chat(request)

        return create_success_response(
            status_code=status.HTTP_200_OK, success_response_model=chat_response
        )
