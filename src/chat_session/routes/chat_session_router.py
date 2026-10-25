from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, status, Request, Depends
from starlette.responses import JSONResponse

from src.chat_session.dependencies import get_chat_session_service
from src.chat_session.schemas.chat_session import CreateChatSession
from src.chat_session.services.chat_session_service import ChatSessionService
from src.middleware.rate_limiter import chat_session_limit
from src.response.delivery import send_success_response

chat_session_router = APIRouter(prefix="/chat-session", tags=["Chat Sessions"])


@chat_session_router.post(
    path="",
    summary="Create a new chat session",
    status_code=status.HTTP_201_CREATED,
)
@chat_session_limit
async def create_new_chat_session(
    request: Request,
    request_body: CreateChatSession,
    chat_session_service: Annotated[
        ChatSessionService, Depends(get_chat_session_service)
    ],
) -> JSONResponse:
    """
    Create a new chat session for the user.
    """
    created = await chat_session_service.create_new_chat_session(
        user_id=request.state.user_id, data=request_body
    )

    return send_success_response(
        message="New chat session was created successfully.",
        status_code=status.HTTP_201_CREATED,
        data=created,
    )


@chat_session_router.post(
    path="/init",
    summary="Initialize a new chat session",
    status_code=status.HTTP_200_OK,
)
@chat_session_limit
async def initialize_chat_session(
    request: Request,
    request_body: CreateChatSession,
    chat_session_service: Annotated[
        ChatSessionService, Depends(get_chat_session_service)
    ],
) -> JSONResponse:
    """
    Initialize a new chat session for the user.
    """
    initialized = await chat_session_service.initialize_chat_session(
        user_id=request.state.user_id, data=request_body
    )

    return send_success_response(
        message="Chat session was initialized successfully.",
        status_code=status.HTTP_200_OK,
        data=initialized,
    )


@chat_session_router.get(
    path="/{chat_session_id}",
    summary="Get chat session details",
    status_code=status.HTTP_200_OK,
)
@chat_session_limit
async def get_chat_session(
    request: Request,
    chat_session_id: UUID,
    chat_session_service: Annotated[
        ChatSessionService, Depends(get_chat_session_service)
    ],
) -> JSONResponse:
    """
    Get the details of a specific chat session by its ID.
    """
    chat_session = await chat_session_service.get_chat_session(
        user_id=request.state.user_id, chat_session_id=chat_session_id
    )

    return send_success_response(
        message="Chat session details retrieved successfully.",
        status_code=status.HTTP_200_OK,
        data=chat_session,
    )


@chat_session_router.delete(
    path="/{chat_session_id}",
    summary="Delete a chat session",
    status_code=status.HTTP_204_NO_CONTENT,
)
@chat_session_limit
async def delete_chat_session(
    request: Request,
    chat_session_id: UUID,
    chat_session_service: Annotated[
        ChatSessionService, Depends(get_chat_session_service)
    ],
) -> JSONResponse:
    """
    Delete a specific chat session by its ID.
    """
    await chat_session_service.delete_chat_session(
        user_id=request.state.user_id, chat_session_id=chat_session_id
    )

    return send_success_response(
        message="Chat session was deleted successfully.",
        status_code=status.HTTP_204_NO_CONTENT,
    )


@chat_session_router.get(
    path="/{chat_session_id}/messages",
    summary="Get chat session messages",
    status_code=status.HTTP_200_OK,
)
@chat_session_limit
async def get_chat_session_messages(
    request: Request,
    chat_session_id: UUID,
    chat_session_service: Annotated[
        ChatSessionService, Depends(get_chat_session_service)
    ],
) -> JSONResponse:
    """
    Get the messages of a specific chat session by its ID.
    """
    messages = await chat_session_service.get_chat_session_messages(
        user_id=request.state.user_id, chat_session_id=chat_session_id
    )

    return send_success_response(
        message="Chat session messages retrieved successfully.",
        status_code=status.HTTP_200_OK,
        data=messages,
    )
