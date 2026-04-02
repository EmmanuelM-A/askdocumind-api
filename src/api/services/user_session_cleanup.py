"""Service for purging expired user sessions and related resources."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select

from src.api.services.caching.cache_factory import CacheFactory
from src.components.chatbot.core import RAGChatbot
from src.config.configs import settings
from src.config.constants import CacheNamespace
from src.database.connection import DatabaseConnection, get_database_connection
from src.database.models import User
from src.database.repository import get_database_repository
from src.database.repository.interfaces import ChatSessionSearchCriteria
from src.database.repository.interfaces.chat_session_repository import (
    ChatSessionRepositoryInterface,
)
from src.database.repository.interfaces.user_repository import UserRepositoryInterface
from src.database.storage import StorageService, get_storage_service
from src.components.chatbot.chatbot_factory import get_chatbot
from src.logger.base_logger import BaseLogger


class UserSessionCleanupService:
    """Purge expired user sessions and their stored resources."""

    def __init__(
        self,
        db_connection: Optional[DatabaseConnection] = None,
        user_repo: Optional[UserRepositoryInterface] = None,
        chat_session_repo: Optional[ChatSessionRepositoryInterface] = None,
        storage_service: Optional[StorageService] = None,
        chatbot: Optional[RAGChatbot] = None,
    ) -> None:
        self._db = db_connection or get_database_connection()
        self.user_repo = user_repo or get_database_repository("USER")
        self.chat_session_repo = chat_session_repo or get_database_repository(
            "CHAT_SESSION"
        )
        self.storage_service = storage_service or get_storage_service()
        self.chatbot = chatbot or get_chatbot()
        self._logger = BaseLogger(__name__)

    async def cleanup_expired_user_sessions(self, batch_size: Optional[int] = None) -> int:
        """Remove expired user sessions and all related resources."""

        effective_batch_size = batch_size or settings.auth.USER_SESSION_CLEANUP_BATCH_SIZE
        expired_users = await self._get_expired_users(batch_size=effective_batch_size)

        if not expired_users:
            self._logger.debug("No expired user sessions found for cleanup.")
            return 0

        cleaned_count = 0

        for user in expired_users:
            chat_sessions = await self.chat_session_repo.list_by(
                ChatSessionSearchCriteria(user_id=user.id)
            )
            chat_ids = [str(chat_session.id) for chat_session in chat_sessions]

            if not self._cleanup_user_resources(user_id=user.id, chat_ids=chat_ids):
                self._logger.warning(
                    f"Skipping deletion of expired user {user.id} because one or more "
                    "resource cleanup steps failed."
                )
                continue

            deleted = await self.user_repo.delete(user.id)
            if deleted:
                cleaned_count += 1
                self._logger.info(f"Purged expired user session: {user.id}")

        return cleaned_count

    async def run_scheduler(
        self,
        stop_event: asyncio.Event,
        interval_minutes: Optional[int] = None,
        batch_size: Optional[int] = None,
    ) -> None:
        """Run periodic cleanup until the stop event is set."""

        effective_interval_minutes = (
            interval_minutes or settings.auth.USER_SESSION_CLEANUP_INTERVAL_MINUTES
        )
        sleep_seconds = max(effective_interval_minutes * 60, 1)
        effective_batch_size = batch_size or settings.auth.USER_SESSION_CLEANUP_BATCH_SIZE

        while not stop_event.is_set():
            await self.cleanup_expired_user_sessions(batch_size=effective_batch_size)

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=sleep_seconds)
            except asyncio.TimeoutError:
                continue

    async def _get_expired_users(self, batch_size: int) -> list[User]:
        """Fetch expired users ordered by expiry time."""

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        async with self._db.get_session() as session:
            stmt = (
                select(User)
                .where(User.expires_at.is_not(None), User.expires_at <= now)
                .order_by(User.expires_at.asc())
                .limit(batch_size)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    def _cleanup_user_resources(self, user_id: UUID, chat_ids: list[str]) -> bool:
        """Best-effort cleanup of files, vectors, and cache entries."""

        success = True

        for chat_id in chat_ids:
            try:
                self.storage_service.delete_all(chat_id)
            except Exception as exc:
                success = False
                self._logger.warning(
                    f"Failed to delete uploaded files for chat {chat_id}: {exc}"
                )

            try:
                if self.chatbot.chat_exists(chat_id):
                    self.chatbot.delete_chat(chat_id)
            except Exception as exc:
                success = False
                self._logger.warning(
                    f"Failed to delete vector resources for chat {chat_id}: {exc}"
                )

        self._clear_cache_namespaces(user_id=user_id, chat_ids=chat_ids)
        return success

    def _clear_cache_namespaces(self, user_id: UUID, chat_ids: list[str]) -> None:
        """Clear any user/session-related cache namespaces for the expired session."""

        prefixes = [str(user_id), *chat_ids]
        for namespace in (
            CacheNamespace.SESSIONS,
            CacheNamespace.QUERIES,
            CacheNamespace.DOCUMENTS,
        ):
            cache = CacheFactory.get_cache(namespace)
            for prefix in prefixes:
                cache.clear_namespace(prefix)


async def run_user_session_cleanup_scheduler(
    stop_event: asyncio.Event,
    interval_minutes: Optional[int] = None,
    batch_size: Optional[int] = None,
    cleanup_service: Optional[UserSessionCleanupService] = None,
) -> None:
    """Convenience wrapper for scheduling periodic user-session cleanup."""

    service = cleanup_service or UserSessionCleanupService()
    await service.run_scheduler(
        stop_event=stop_event,
        interval_minutes=interval_minutes,
        batch_size=batch_size,
    )


