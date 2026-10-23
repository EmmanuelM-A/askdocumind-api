"""
Shared services for the project.
"""

import logging
from uuid import UUID

from src.auth.models.user import User
from src.auth.repository.user_repository import UserRepository
from src.chat_session.models.chat_session import ChatSession
from src.chat_session.repository.chat_session_repository import ChatSessionRepository
from src.exceptions import not_found_error, forbidden_error

_logger = logging.getLogger(__name__)


class BaseService:
    """
    Base class for services that require a database session manager.
    """

    def __init__(
        self,
        user_repository: UserRepository,
        chat_session_repository: ChatSessionRepository,
    ) -> None:
        self._user_repository = user_repository
        self._chat_session_repository = chat_session_repository

    async def _verify_user_exists(self, user_id: UUID) -> User:
        """
        Verify that a user exists in the system.
        Raises an exception if the user does not exist.
        """
        user = await self._user_repository.get_by_id(user_id)
        if user is None:
            raise not_found_error(
                message=f"The user with provided id does not exist",
                error_code="USER_NOT_FOUND",
            )
        _logger.debug("The user '%s' exists in the system.", user_id)

        return user

    async def _verify_user_owns_chat_session(
        self, user_id: UUID, chat_session_id: UUID
    ) -> ChatSession:
        """
        Verify that a user owns a specific chat session.
        Raises an exception if the user does not own the chat session.
        """
        chat_session = await self._chat_session_repository.get_by_id(chat_session_id)
        if chat_session is None:
            raise not_found_error(
                message="The chat session with provided id does not exist",
                error_code="CHAT_SESSION_NOT_FOUND",
            )
        if chat_session.user_id != user_id:
            raise forbidden_error(
                message="The user does not have permission to access this chat session",
                error_code="ACCESS_DENIED",
            )
        _logger.debug(
            "The user '%s' owns the chat session '%s'.", user_id, chat_session_id
        )

        return chat_session
