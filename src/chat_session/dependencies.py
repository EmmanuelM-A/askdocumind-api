from typing import Annotated

from fastapi import Depends

from src.auth.dependencies import get_user_repository
from src.auth.repository.user_repository import UserRepository
from src.chat_session.repository.chat_message_repository import ChatMessageRepository
from src.chat_session.repository.chat_message_repository_impl import (
    ChatMessageRepositoryImpl,
)
from src.chat_session.repository.chat_session_repository import ChatSessionRepository
from src.chat_session.repository.chat_session_repository_impl import (
    ChatSessionRepositoryImpl,
)
from src.chat_session.services.chat_session_service import ChatSessionService
from src.database.dependencies import DbSession


def get_chat_session_repository(session: DbSession) -> ChatSessionRepository:
    """
    Provide a ChatSessionRepository bound to the current request's session.
    """
    return ChatSessionRepositoryImpl(session)


def get_chat_message_repository(session: DbSession) -> ChatMessageRepository:
    """
    Provide a ChatMessageRepository bound to the current request's session.
    """
    return ChatMessageRepositoryImpl(session)


def get_chat_session_service(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    chat_session_repository: Annotated[
        ChatSessionRepository, Depends(get_chat_session_repository)
    ],
    chat_message_repository: Annotated[
        ChatMessageRepository, Depends(get_chat_message_repository)
    ],
) -> ChatSessionService:
    """
    Provide a ChatSessionService for the current request.
    """
    return ChatSessionService(
        user_repository=user_repository,
        chat_session_repository=chat_session_repository,
        chat_message_repository=chat_message_repository,
    )
