from datetime import datetime, timedelta, timezone
from typing import List, cast
from uuid import UUID

from alembic.environment import Optional
from src.database.models import User
from src.database.repository.interfaces import UserRepositoryInterface
from src.api.utils.session_manager import TokenManager
from src.logger.base_logger import BaseLogger
from src.config.configs import settings


class AnonymousUserSessionService:
    """
    Service for managing anonymous user sessions, including creation and activity updates.
    """

    def __init__(
        self, user_repo: UserRepositoryInterface, token_manager: TokenManager
    ) -> None:
        self._user_repo = user_repo
        self._token_manager: TokenManager = token_manager
        self._logger = BaseLogger(__name__)

    async def _create_anonymous_user_session(self) -> UUID:
        """
        Create a new anonymous user session and return its UUID.
        """

        anonymous_user = User(last_seen_at=datetime.now(timezone.utc))

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
            self._logger.debug(
                "No anonymous session cookie found, creating new session."
            )
            return await self._create_anonymous_user_session()

        try:
            payload = self._token_manager.decode_token(cookie_value)
        except Exception:
            self._logger.debug("Anonymous session cookie could not be reused.")
            return await self._create_anonymous_user_session()
        
        existing_user = await self._user_repo.get_by_id(payload.user_id)

        if existing_user is None:
            self._logger.debug(
                "Anonymous session cookie did not match any user, creating new session."
            )
            return await self._create_anonymous_user_session()

        await self._user_repo.update_last_seen(user_id=cast(UUID, existing_user.id))

        self._logger.info(f"Reused existing anonymous user session {existing_user.id}")

        return cast(UUID, existing_user.id)

    async def delete_expired_anonymous_user_sessions(
        self, batch_size: int = settings.anon.BATCH_SIZE
    ) -> int:
        """
        Deletes expired anonymous user sessions in batches.

        :param batch_size: Number of sessions to delete in each batch.
        :return: Total number of deleted sessions.
        """

        cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=settings.anon.TTL_MINS / 60
        )

        expired_ids: List[UUID] = await self._user_repo.get_all_expired_user_ids(
            cutoff=cutoff
        )

        if len(expired_ids) == 0:
            self._logger.info("No expired anonymous user sessions found.")
            return 0

        self._logger.debug(
            f"Found {len(expired_ids)} expired user session(s) to clean up."
        )

        total_deleted = 0
        failed_deletions = 0

        for i in range(0, len(expired_ids), batch_size):
            batch = expired_ids[i : i + batch_size]

            try:
                total_deleted += await self._user_repo.delete_many(batch)
            except Exception as exc:
                failed_deletions += len(batch)
                self._logger.warning(
                    f"Failed to delete expired user batch {i // batch_size + 1}: {exc}"
                )

        self._logger.info(
            f"Cleanup complete: {total_deleted} expired session(s) purged, {failed_deletions} failed deletions."
        )
        return total_deleted
