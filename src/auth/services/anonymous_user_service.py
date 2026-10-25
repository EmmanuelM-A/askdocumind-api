import logging

from src.auth.domain.auth import AnonymousTokenPayload
from src.auth.models.mapper import ViewableUser
from src.auth.models.user import User
from src.auth.repository.user_repository import UserRepository
from src.auth.services.token_service import (
    decode_anonymous_token,
    create_anonymous_token,
)
from src.config.configs import settings

_logger = logging.getLogger(__name__)


class AnonymousUserService:
    """
    Service class for managing anonymous users and their session tokens.
    """

    def __init__(self, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    async def init_anonymous_user(
        self, anonymous_token: str | None = None
    ) -> tuple[ViewableUser, str]:
        """
        Initialize an anonymous user session. If a valid token is provided,
        it will return the existing user; otherwise, it will create a new
        anonymous user.
        """
        token = (anonymous_token or "").strip()

        if not token:
            return await self._create_anonymous_user()

        payload: AnonymousTokenPayload = decode_anonymous_token(token)

        db_user = await self._user_repository.get_by_id(payload.user_id)

        if db_user is None:
            return await self._create_anonymous_user()

        await self._user_repository.update_last_seen(
            user_id=db_user.id, freq_mins=settings.auth.UPDATE_LAST_SEEN_FREQ_MINS
        )

        _logger.debug("Returning existing anonymous user '%s'", db_user.id)

        # A fresh token keeps its expiry in step with the cookie, which is
        # reset on every init, so active users are not signed out
        return db_user.viewable(), create_anonymous_token(db_user.id)

    async def _create_anonymous_user(self) -> tuple[ViewableUser, str]:
        """
        Create a new anonymous user and generate its associated session token
        for them.
        """
        created_user = await self._user_repository.create(User())
        anonymous_token = create_anonymous_token(created_user.id)

        _logger.debug("Created a new anonymous user '%s'", created_user.id)

        return created_user.viewable(), anonymous_token
