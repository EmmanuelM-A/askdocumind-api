"""Cleanup orchestration for anonymous user resources."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from src.api.services.caching.cache_factory import CacheFactory
from src.components.chatbot.chatbot_factory import get_chatbot
from src.components.chatbot.core import RAGChatbot
from src.config.configs import settings
from src.config.constants import CacheNamespace
from src.database.models import User
from src.database.repository import get_database_repository
from src.database.repository.database_repository_factory import get_tx_factory
from src.database.repository.interfaces import (
    ChatSessionRepositoryInterface,
    ChatSessionSearchCriteria,
    DBTransactionFactory,
    UserRepositoryInterface,
)
from src.database.storage import StorageService, get_storage_service
from src.logger.base_logger import BaseLogger


class CleanupAnonymousUserResources:
    def __init__(
        self,
        user_repo: UserRepositoryInterface,
        chat_repo: ChatSessionRepositoryInterface,
        tx_factory: DBTransactionFactory,
        chatbot: RAGChatbot,
        storage_service: StorageService,
    ) -> None:
        self.user_repo = user_repo
        self.chat_repo = chat_repo
        self.tx_factory = tx_factory
        self.chatbot = chatbot
        self.storage_service = storage_service
        self.logger = BaseLogger(__name__)

    async def _get_expired_user_ids(self, cutoff: datetime) -> list[UUID]:
        """Fetch expired anonymous user IDs before attempting cleanup."""

        async with self.tx_factory.create() as tx:
            stmt = select(User.id).where(
                User.last_seen_at.is_not(None),
                User.last_seen_at <= cutoff,
            )
            result = await tx.execute(stmt)
            return list(result.scalars().all())

    async def _cleanup_expired_anonymous_user_sessions(self) -> int:
        """Delete expired anonymous users and clear related resources."""

        cutoff = datetime.now() - timedelta(
            hours=settings.auth.ANON_SESSION_TTL_HOURS
        )

        expired_user_ids = await self._get_expired_user_ids(cutoff)
        if not expired_user_ids:
            return 0

        deleted_count = 0

        for user_id in expired_user_ids:
            try:
                async with self.tx_factory.create() as tx:
                    chat_sessions = await self.chat_repo.list_by(
                        criteria=ChatSessionSearchCriteria(user_id=user_id),
                        tx=tx,
                    )
                    chat_ids = [str(chat_session.id) for chat_session in chat_sessions]

                    resources_ok = self._clear_additional_resources(chat_ids)
                    self._clear_caches(chat_ids)

                    if not resources_ok:
                        self.logger.warning(
                            f"Skipping deletion for user {user_id} because one or more non-DB resources failed to clear."
                        )
                        continue

                    if await self.user_repo.delete(user_id, tx=tx):
                        deleted_count += 1

            except Exception as exc:
                self.logger.warning(
                    f"Failed cleanup transaction for expired user {user_id}: {exc}"
                )

        if deleted_count > 0:
            self.logger.debug(
                f"Deleted {deleted_count} expired anonymous user session(s)"
            )

        return deleted_count

    def _clear_caches(self, chat_ids: list[str]) -> None:
        """Clear chat-scoped cache entries for deleted sessions."""

        if not chat_ids:
            return

        for namespace in (
            CacheNamespace.SESSIONS,
            CacheNamespace.QUERIES,
            CacheNamespace.DOCUMENTS,
        ):
            cache = CacheFactory.get_cache(namespace)
            for chat_id in chat_ids:
                try:
                    cache.clear_namespace(chat_id)
                except Exception as exc:
                    self.logger.warning(
                        f"Failed to clear cache for namespace={namespace} chat_id={chat_id}: {exc}"
                    )

    def _clear_additional_resources(self, chat_ids: list[str]) -> bool:
        """Clear storage files and vector indexes for deleted sessions."""

        if not chat_ids:
            return True

        success = True

        for chat_id in chat_ids:
            try:
                self.storage_service.delete_all(chat_id)
            except Exception as exc:
                success = False
                self.logger.warning(
                    f"Failed to delete storage resources for chat {chat_id}: {exc}"
                )

            try:
                if self.chatbot.chat_exists(chat_id):
                    self.chatbot.delete_chat(chat_id)
            except Exception as exc:
                success = False
                self.logger.warning(
                    f"Failed to delete vector resources for chat {chat_id}: {exc}"
                )

        return success

    async def run_scheduler(
        self,
        stop_event: asyncio.Event,
        interval_minutes: int,
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
    tx_factory=get_tx_factory(),
    chatbot=get_chatbot(),
    storage_service=get_storage_service(),
)


async def init_anon_user_sessions_cleanup(
    stop_event: asyncio.Event = asyncio.Event(),
    interval_minutes: int = settings.auth.USER_SESSION_CLEANUP_INTERVAL_MINUTES,
) -> None:
    """
    Start cleanup repeatedly until the stop event is set.
    """

    if not settings.auth.USER_SESSION_CLEANUP_ENABLED:
        return

    await _cleanup_anon_user_resources.run_scheduler(
        stop_event=stop_event,
        interval_minutes=interval_minutes,
    )
