"""
This module contains the implementation of the UserRepository interface
using SQLAlchemy for database interactions.
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, delete, update, func

from src.auth.models.user import User
from src.auth.repository.user_repository import UserRepository
from src.database import DBTransaction, DatabaseSessionManager, DBTransactionFactory
from src.exceptions import database_error

_logger = logging.getLogger(__name__)


class UserRepositoryImpl(UserRepository):

    def __init__(
        self, session_manager: DatabaseSessionManager, tx_factory: DBTransactionFactory
    ) -> None:
        self._session_manager = session_manager
        self._tx_factory = tx_factory

    async def create(self, data: User, tx: DBTransaction | None = None) -> User:
        try:
            if tx is not None:
                await tx.add(data)
                await tx.flush()
            else:
                async with self._session_manager.get_session() as session:
                    session.add(data)
                    await session.flush()

            return data
        except Exception as e:
            raise database_error(
                message="An error occurred while creating a new user.",
                error_code="USER_CREATION_ERROR",
                cause=e,
            ) from e

    async def get_by_id(
        self, user_id: UUID, tx: DBTransaction | None = None
    ) -> User | None:
        statement = select(User).where(User.id == user_id)
        try:
            return await self._fetch_one(statement, tx=tx)
        except Exception as e:
            raise database_error(
                message="An error occurred while retrieving the user by ID.",
                error_code="USER_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def delete(self, user_id: UUID, tx: DBTransaction | None = None) -> bool:
        statement = delete(User).where(User.id == user_id)
        try:
            result = await self._execute_statement(statement, tx=tx)
            return result.rowcount > 0
        except Exception as e:
            raise database_error(
                message="An error occurred while deleting the user.",
                error_code="USER_DELETION_ERROR",
                cause=e,
            ) from e

    async def delete_many(
        self, user_ids: list[UUID], tx: DBTransaction | None = None
    ) -> int:
        if not user_ids:
            return 0

        statement = delete(User).where(User.id.in_(user_ids))
        try:
            result = await self._execute_statement(statement, tx=tx)
            return result.rowcount
        except Exception as e:
            raise database_error(
                message="An error occurred while deleting multiple users.",
                error_code="USER_DELETION_ERROR",
                cause=e,
            ) from e

    async def update_last_seen(
        self, user_id: UUID, freq_mins: int, tx: DBTransaction | None = None
    ) -> None:
        statement = (
            update(User)
            .where(User.id == user_id)
            .where(User.last_seen_at < func.now() - timedelta(minutes=freq_mins))
            .values(last_seen_at=func.now())
        )
        try:
            await self._execute_statement(statement, tx=tx)
        except Exception as e:
            raise database_error(
                message="An error occurred while updating the user's last seen timestamp.",
                error_code="USER_UPDATE_ERROR",
                cause=e,
            ) from e

    async def get_expired_users(
        self, cutoff: datetime, tx: DBTransaction | None = None
    ) -> list[UUID]:
        statement = select(User.id).where(User.last_seen_at < cutoff)
        try:
            result = await self._execute_statement(statement, tx=tx)
            return list(result.scalars().all())
        except Exception as e:
            raise database_error(
                message="An error occurred while retrieving expired users.",
                error_code="USER_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def _execute_statement(
        self, statement, tx: DBTransaction | None = None
    ) -> Any:
        """Run a statement in the given transaction or in a new session."""
        if tx is not None:
            return await tx.execute(statement)

        async with self._session_manager.get_session() as session:
            return await session.execute(statement)

    async def _fetch_one(
        self, statement, tx: DBTransaction | None = None
    ) -> User | None:
        result = await self._execute_statement(statement, tx=tx)
        return result.scalar_one_or_none()
