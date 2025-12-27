from fastapi import status
from starlette.responses import JSONResponse

from src.services.rag_chatbot import ChatbotService
from src.utils.response_delivery import create_success_response


class RAGChatbotController:
    def __init__(self):
        self.rag_chatbot_service = ChatbotService()

    async def chat(self) -> JSONResponse:
        """Handle chat requests."""

        chat_response = await self.rag_chatbot_service.handle_chat()

        return create_success_response(
            status_code=status.HTTP_200_OK, success_response_model=chat_response
        )
