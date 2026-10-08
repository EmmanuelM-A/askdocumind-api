"""
This module contains the implementation of the UserRepository interface
using SQLAlchemy for database interactions.
"""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models.user import User
from src.auth.repository.user_repository import UserRepository
from src.database.utils import BaseRepository
from src.exceptions import database_error

_logger = logging.getLogger(__name__)


class UserRepositoryImpl(UserRepository, BaseRepository):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._session = session

    async def create(self, data: User) -> User:
        try:
            self._session.add(data)
            await self._session.flush()
            return data
        except Exception as e:
            raise database_error(
                message="An error occurred while creating a new user.",
                error_code="USER_CREATION_ERROR",
                cause=e,
            ) from e

    async def get_by_id(self, user_id: UUID) -> User | None:
        try:
            return await self._fetch_one(select(User).where(User.id == user_id))
        except Exception as e:
            raise database_error(
                message="An error occurred while retrieving the user by ID.",
                error_code="USER_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def delete(self, user_id: UUID) -> bool:
        try:
            result = await self._execute_statement(
                delete(User).where(User.id == user_id)
            )
            return result.rowcount > 0
        except Exception as e:
            raise database_error(
                message="An error occurred while deleting the user.",
                error_code="USER_DELETION_ERROR",
                cause=e,
            ) from e

    async def delete_many(self, user_ids: list[UUID]) -> int:
        if not user_ids:
            return 0

        try:
            result = await self._execute_statement(
                delete(User).where(User.id.in_(user_ids))
            )
            return result.rowcount
        except Exception as e:
            raise database_error(
                message="An error occurred while deleting multiple users.",
                error_code="USER_DELETION_ERROR",
                cause=e,
            ) from e

    async def update_last_seen(self, user_id: UUID, freq_mins: int) -> None:
        statement = (
            update(User)
            .where(User.id == user_id)
            .where(User.last_seen_at < func.now() - timedelta(minutes=freq_mins))
            .values(last_seen_at=func.now())
        )
        try:
            await self._execute_statement(statement)
        except Exception as e:
            raise database_error(
                message="An error occurred while updating the user's last seen timestamp.",
                error_code="USER_UPDATE_ERROR",
                cause=e,
            ) from e

    async def get_expired_users(self, cutoff: datetime) -> list[UUID]:
        statement = select(User.id).where(User.last_seen_at < cutoff)
        try:
            result = await self._execute_statement(statement)
            return list(result.scalars().all())
        except Exception as e:
            raise database_error(
                message="An error occurred while retrieving expired users.",
                error_code="USER_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def _fetch_one(self, statement) -> User | None:
        """
        Fetch a single record from the database based on the provided statement.
        """
        result = await self._execute_statement(statement)
        return result.scalar_one_or_none()
