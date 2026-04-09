from datetime import datetime, timezone, timedelta
from uuid import UUID

from src.api.services.auth.anonymous_identity import (
    get_current_anonymous_user_id,
    set_current_anonymous_user_id,
)
from src.api.utils.cookie_manager import clear_cookie
from src.database.models import User
from src.database.repository.interfaces import (
    UserRepositoryInterface,
    UserSearchCriteria,
    UpdatedUserData,
)
from src.api.utils.session_manager import get_token_manager
from src.logger.base_logger import BaseLogger


class AnonymousUserSessionService:
    """
    Handles the creation and deletion of an anonymous user session.
    This allows users to interact with the application without needing to
    create an account, while still enabling session management and cleanup of
    stale sessions.
    """

    def __init__(
        self, user_repo: UserRepositoryInterface, ttl_hours: float = 0.5
    ) -> None:
        self.user_repo = user_repo
        self.ttl_hours = ttl_hours
        self.logger = BaseLogger(__name__)

    async def _create_anonymous_user(self) -> UUID:
        """
        Creates a new anonymous user session.
        :return: The UUID of the created session.
        """
        anonymous_user = User(
            last_seen_at=datetime.now(timezone.utc).replace(tzinfo=None)
        )

        anonymous_id = await self.user_repo.create(anonymous_user)

        set_current_anonymous_user_id(anonymous_id)

        self.logger.debug("Created new anonymous user session")

        return anonymous_id

    async def init_anonymous_user_session(
        self, cookie_value: str | None = None
    ) -> UUID:
        """
        Initializes an anonymous user session.

        Reuses an existing request-context user first, then attempts to reuse
        the cookie-backed session, and falls back to creating a new anonymous
        user if needed.
        """
        current_user_id = get_current_anonymous_user_id()
        if current_user_id is not None:
            return current_user_id

        token_manager = get_token_manager()

        if cookie_value:
            try:
                payload = token_manager.decode_token(cookie_value)
                existing_user = await self.user_repo.get_by_id(payload.user_id)

                if existing_user is not None:
                    set_current_anonymous_user_id(existing_user.id)
                    await self.user_repo.update(
                        existing_user.id,
                        UpdatedUserData(
                            last_seen_at=datetime.now(timezone.utc).isoformat()
                        ),
                    )
                    return existing_user.id
            except Exception:
                self.logger.debug("Anonymous session cookie could not be reused.")

        return await self._create_anonymous_user()

    async def cleanup_anonymous_user_sessions(self) -> int:
        """
        Deletes all anonymous user sessions that have expired.
        """
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            hours=self.ttl_hours
        )
        deleted_count = await self.user_repo.delete_by_criteria(
            UserSearchCriteria(last_seen_at_lte=cutoff)
        )

        if deleted_count > 0:
            self.logger.debug(
                f"Deleted {deleted_count} expired anonymous user session(s)"
            )

        return deleted_count

    async def update_anonymous_user_activity(self) -> None:
        """
        Updates the last seen timestamp of the current anonymous user session.
        """
        current_user_id = get_current_anonymous_user_id()
        if current_user_id is None:
            return
        await self.user_repo.update(
            current_user_id,
            UpdatedUserData(last_seen_at=datetime.now(timezone.utc).isoformat()),
        )
