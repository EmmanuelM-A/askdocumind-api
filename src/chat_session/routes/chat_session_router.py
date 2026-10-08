from fastapi import APIRouter, status

chat_session_router = APIRouter(prefix="/chat-session", tags=["Chat Sessions"])


@chat_session_router.post(
    path="",
    summary="Create a new chat session",
    status_code=status.HTTP_201_CREATED,
)
async def create_new_chat_session():
    pass


@chat_session_router.post(
    path="/init",
    summary="Initialize a new chat session",
    status_code=status.HTTP_200_OK,  # NOTE: Check if this should be 201 instead of 200
)
async def initialize_chat_session():
    pass


@chat_session_router.get(
    path="/{chat_session_id}",
    summary="Get chat session details",
    status_code=status.HTTP_200_OK,
)
async def get_chat_session():
    pass


@chat_session_router.delete(
    path="/{chat_session_id}",
    summary="Delete a chat session",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chat_session():
    pass


@chat_session_router.get(
    path="/{chat_session_id}/messages",
    summary="Get chat session messages",
    status_code=status.HTTP_200_OK,
)
async def get_chat_session_messages():
    pass
