"""
This module contains the implementation of the UserRepository interface
using SQLAlchemy for database interactions.
"""

import logging
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models.user import User
from src.auth.repository.user_repository import UserRepository
from src.database.utils import BaseRepository
from src.exceptions.decorators import (
    handle_database_unavailable_exceptions,
    handle_sqlalchemy_exceptions,
)

_logger = logging.getLogger(__name__)


class UserRepositoryImpl(UserRepository, BaseRepository):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    @handle_sqlalchemy_exceptions(
        message="An error occurred while creating a new user.",
        error_code="USER_CREATION_ERROR",
    )
    @handle_database_unavailable_exceptions()
    async def create(self, data: User) -> User:
        self._session.add(data)
        await self._session.flush()
        return data

    @handle_sqlalchemy_exceptions(
        message="An error occurred while retrieving the user by ID.",
        error_code="USER_RETRIEVAL_ERROR",
    )
    @handle_database_unavailable_exceptions()
    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self._fetch_one(select(User).where(User.id == user_id))

    @handle_sqlalchemy_exceptions(
        message="An error occurred while deleting the user.",
        error_code="USER_DELETION_ERROR",
    )
    @handle_database_unavailable_exceptions()
    async def delete(self, user_id: UUID) -> bool:
        result = await self._session.execute(delete(User).where(User.id == user_id))
        return result.rowcount > 0

    @handle_sqlalchemy_exceptions(
        message="An error occurred while deleting multiple users.",
        error_code="USER_DELETION_ERROR",
    )
    @handle_database_unavailable_exceptions()
    async def delete_many(self, user_ids: list[UUID]) -> int:
        if not user_ids:
            return 0

        result = await self._session.execute(delete(User).where(User.id.in_(user_ids)))
        return result.rowcount

    @handle_sqlalchemy_exceptions(
        message="An error occurred while updating the user's last seen timestamp.",
        error_code="USER_UPDATE_ERROR",
    )
    @handle_database_unavailable_exceptions()
    async def update_last_seen(self, user_id: UUID, freq_mins: int) -> None:
        statement = (
            update(User)
            .where(User.id == user_id)
            .where(User.last_seen_at < func.now() - timedelta(minutes=freq_mins))
            .values(last_seen_at=func.now())
            .execution_options(synchronize_session=False)
        )
        # NOTE: The User entity in memory will not be updated with the new
        # NOTE: last_seen_at value after this operation.

        await self._session.execute(statement)

    async def _fetch_one(self, statement) -> User | None:
        """
        Fetch a single record from the database based on the provided statement.
        """
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()
