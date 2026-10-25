"""
Database queries used to remove expired anonymous users.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select

from src.auth.models.user import User
from src.chat_session.models.chat_session import ChatSession
from src.database.utils import BaseRepository
from src.exceptions.decorators import (
    handle_database_unavailable_exceptions,
    handle_sqlalchemy_exceptions,
)


class ExpiredUserRepository(BaseRepository):

    @handle_sqlalchemy_exceptions(
        message="An error occurred while selecting expired users.",
        error_code="EXPIRED_USER_RETRIEVAL_ERROR",
    )
    @handle_database_unavailable_exceptions()
    async def lock_expired_users(self, cutoff: datetime, limit: int) -> list[UUID]:
        """
        Lock up to limit users last seen before cutoff, oldest first. Rows
        locked by another transaction are skipped, so two cleaners never
        claim the same user.
        """
        statement = (
            select(User.id)
            .where(User.last_seen_at < cutoff)
            .order_by(User.last_seen_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        result = await self._session.execute(statement)
        return list(result.scalars().all())

    @handle_sqlalchemy_exceptions(
        message="An error occurred while listing the chat sessions of expired users.",
        error_code="EXPIRED_USER_RETRIEVAL_ERROR",
    )
    @handle_database_unavailable_exceptions()
    async def list_chat_session_ids(self, user_ids: list[UUID]) -> list[UUID]:
        if not user_ids:
            return []

        statement = select(ChatSession.id).where(ChatSession.user_id.in_(user_ids))

        result = await self._session.execute(statement)
        return list(result.scalars().all())

    @handle_sqlalchemy_exceptions(
        message="An error occurred while deleting expired users.",
        error_code="EXPIRED_USER_DELETION_ERROR",
    )
    @handle_database_unavailable_exceptions()
    async def delete_users(self, user_ids: list[UUID]) -> int:
        """
        Delete the users. The foreign keys cascade to their chat sessions,
        messages, documents and chunk embeddings.
        """
        if not user_ids:
            return 0

        result = await self._session.execute(delete(User).where(User.id.in_(user_ids)))
        return result.rowcount
