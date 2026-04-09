"""Cleanup orchestration for anonymous user resources."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from src.api.services.caching.cache_factory import CacheFactory
from src.config.configs import settings
from src.config.constants import CacheNamespace
from src.database.repository import get_database_repository
from src.database.repository.interfaces import (
    UserRepositoryInterface,
    ChatSessionRepositoryInterface,
    UserSearchCriteria,
)
from src.logger.base_logger import BaseLogger


class CleanupAnonymousUserResources:
    def __init__(
        self,
        user_repo: UserRepositoryInterface,
        chat_repo: ChatSessionRepositoryInterface,
    ) -> None:
        self.user_repo = user_repo
        self.chat_repo = chat_repo
        self.logger = BaseLogger(__name__)

    async def _cleanup_expired_anonymous_user_sessions(self) -> int:
        """Delete anonymous users whose last_seen_at is older than the TTL."""

        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            hours=settings.auth.ANON_SESSION_TTL_HOURS
        )

        deleted_count = await self.user_repo.delete_by_criteria(
            UserSearchCriteria(last_seen_at_lte=cutoff)
        )

        if deleted_count > 0:
            self.logger.debug(
                f"Deleted {deleted_count} expired anonymous user session(s)"
            )

        return deleted_count

    def _clear_caches(self):
        pass

    def _clear_additional_resources(self):
        pass

    async def run_scheduler(
        self,
        stop_event: Optional[asyncio.Event] = None,
        interval_minutes: Optional[int] = None,
    ) -> None:
        """Run cleanup repeatedly until the stop event is set."""

        sleep_seconds = max(interval_minutes * 60, 1)

        while not stop_event.is_set():
            await self._cleanup_expired_anonymous_user_sessions()

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=sleep_seconds)
            except asyncio.TimeoutError:
                continue


_cleanup_anon_user_resources = CleanupAnonymousUserResources(
    user_repo=get_database_repository("USER"),
    chat_repo=get_database_repository("CHAT_SESSION"),
)


async def init_anon_user_sessions_cleanup(
    stop_event: asyncio.Event = asyncio.Event(),
    interval_minutes: Optional[
        int
    ] = settings.auth.USER_SESSION_CLEANUP_INTERVAL_MINUTES,
) -> None:
    """
    Start cleanup repeatedly until the stop event is set.
    """

    await _cleanup_anon_user_resources.run_scheduler(
        stop_event=stop_event,
        interval_minutes=interval_minutes,
    )
