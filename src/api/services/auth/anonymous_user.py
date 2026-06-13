from datetime import datetime
from typing import cast
from uuid import UUID

from alembic.environment import Optional

from src.api.utils.helper import timestamp_now
from src.database.models import User
from src.database.repository.interfaces import (
    UserRepositoryInterface,
    UpdatedUserData,
)
from src.api.utils.session_manager import TokenManager, get_token_manager
from src.logger.base_logger import BaseLogger


class AnonymousUserSessionService:
    """
    Service for managing anonymous user sessions, including creation and activity updates.
    """

    def __init__(
        self,
        user_repo: UserRepositoryInterface,
        token_manager: TokenManager
    ) -> None:
        self._user_repo = user_repo
        self._token_manager: TokenManager = token_manager
        self._logger = BaseLogger(__name__)

    async def _create_anonymous_user_session(self) -> UUID:
        """
        Create a new anonymous user session and return its UUID.
        """

        anonymous_user = User(last_seen_at=timestamp_now())

        anonymous_id = await self._user_repo.create(anonymous_user)

        self._logger.debug("Created a new anonymous user session")

        return anonymous_id

    async def init_anonymous_user_session(
        self, cookie_value: Optional[str] = None
    ) -> UUID:
        """
        Initializes an anonymous user session.

        If a cookie value is provided, it attempts to decode and validate the session.
        If valid, it updates the last seen timestamp. If not valid or no cookie is provided,
        it creates a new anonymous user session.
        """

        if cookie_value is None:
            self._logger.debug("No anonymous session cookie found, creating new session.")
            return await self._create_anonymous_user_session()
        
        existing_user: Optional[User] = None

        try:
            payload = self._token_manager.decode_token(cookie_value)
            existing_user = await self._user_repo.get_by_id(payload.user_id)
        except Exception:
            self._logger.debug("Anonymous session cookie could not be reused.")
            return await self._create_anonymous_user_session()
        
        if existing_user is None:
            self._logger.debug("Anonymous session cookie did not match any user, creating new session.")
            return await self._create_anonymous_user_session()
        
        await self._user_repo.update_last_seen(user_id=cast(UUID, existing_user.id))
        
        self._logger.info(f"Reused existing anonymous user session {existing_user.id}")
        
        return cast(UUID, existing_user.id)
