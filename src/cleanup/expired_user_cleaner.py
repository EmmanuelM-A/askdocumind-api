"""
Background job which deletes expired anonymous users and everything they own.
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from src.cleanup.expired_user_repository import ExpiredUserRepository
from src.config.configs import settings
from src.database.session import DatabaseSessionManager
from src.uploads.storage.object_storage import ObjectStorage

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExpiredUserCleanerConfig:
    interval_seconds: int = 900
    batch_limit: int = 100
    # Extra time after a user's token must have expired before deleting them
    grace_seconds: int = 600


class ExpiredUserCleaner:
    def __init__(
        self,
        session_manager: DatabaseSessionManager,
        storage: ObjectStorage,
        config: ExpiredUserCleanerConfig,
    ) -> None:
        self._session_manager = session_manager
        self._storage = storage
        self._config = config
        self._task: asyncio.Task | None = None

    # ------------------------ Lifecycle ------------------------

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="expired-user-cleaner")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.clean_once()
            except Exception:
                _logger.exception("The expired user cleanup pass failed.")
            await asyncio.sleep(self._config.interval_seconds)

    async def clean_once(self) -> int:
        """
        Delete every expired user, one batch at a time, and return how many
        were deleted.
        """
        total = 0

        while True:
            deleted = await self._clean_batch(self.cutoff())
            total += deleted
            if deleted < self._config.batch_limit:
                break

        if total:
            _logger.info("Deleted %s expired anonymous users.", total)

        return total

    def cutoff(self) -> datetime:
        """
        Users last seen before this time have an expired token. A token lasts
        ANONYMOUS_TOKEN_TTL_HOURS from the user's last init, and last_seen_at
        can lag that init by up to UPDATE_LAST_SEEN_FREQ_MINS.
        """
        inactive_for = timedelta(
            hours=settings.auth.ANONYMOUS_TOKEN_TTL_HOURS,
            minutes=settings.auth.UPDATE_LAST_SEEN_FREQ_MINS,
            seconds=self._config.grace_seconds,
        )
        return datetime.now(UTC) - inactive_for

    # ------------------------ Helpers ------------------------

    async def _clean_batch(self, cutoff: datetime) -> int:
        async with self._session_manager.get_session() as session:
            repository = ExpiredUserRepository(session)

            user_ids = await repository.lock_expired_users(
                cutoff, self._config.batch_limit
            )
            if not user_ids:
                return 0

            chat_session_ids = await repository.list_chat_session_ids(user_ids)
            await repository.delete_users(user_ids)

        # Files go after the commit, so a failed commit never leaves rows
        # pointing at deleted files
        await self._delete_files(chat_session_ids)

        return len(user_ids)

    async def _delete_files(self, chat_session_ids: list[UUID]) -> None:
        for chat_session_id in chat_session_ids:
            try:
                await asyncio.to_thread(
                    self._storage.delete_prefix, f"{chat_session_id}/"
                )
            except Exception:
                _logger.exception(
                    "Failed to delete the files of chat session '%s'.",
                    chat_session_id,
                )
