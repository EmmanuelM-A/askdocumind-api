from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from starlette.responses import JSONResponse

from src.chatbot.dependencies import get_chatbot_service
from src.chatbot.schemas.chatbot import ChatRequest
from src.chatbot.services.chatbot_service import ChatbotService
from src.response.delivery import send_success_response

chatbot_router = APIRouter(prefix="/chatbot", tags=["Chatbot"])


@chatbot_router.post(
    path="/{chat_session_id}/ask",
    summary="Ask a question about the chat session's documents",
    status_code=status.HTTP_200_OK,
)
async def ask_question(
    request: Request,
    chat_session_id: UUID,
    request_body: ChatRequest,
    chatbot_service: Annotated[ChatbotService, Depends(get_chatbot_service)],
) -> JSONResponse:
    """
    Answer a question using the chat session's documents and, when enabled,
    a web search.
    """
    response = await chatbot_service.handle_chat_request(
        data=request_body,
        chat_session_id=chat_session_id,
        authenticated_user_id=request.state.user_id,
    )

    return send_success_response(
        message="The question was answered successfully.",
        status_code=status.HTTP_200_OK,
        data=response,
    )
