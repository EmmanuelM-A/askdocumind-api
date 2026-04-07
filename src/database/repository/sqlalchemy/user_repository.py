"""
Concrete implementation of the user repository, providing methods for CRUD
operations and specific queries related to user entities.
"""

from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, func, delete
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from src.database.connection import DatabaseConnection
from src.database.models import User
from src.database.repository.interfaces.user_repository import (
    UserRepositoryInterface,
    UserSearchCriteria,
    UpdatedUserData,
)
from src.database.repository.interfaces.db_transaction import DBTransaction
from src.errors.custom_exceptions import database_error
from src.logger.base_logger import BaseLogger


class UserRepository(UserRepositoryInterface):
    """
    Concrete implementation of the user repository interface.
    """

    def __init__(self, connection: DatabaseConnection) -> None:
        self._db = connection
        self._logger = BaseLogger(__name__)

    @staticmethod
    def _build_filters(criteria: UserSearchCriteria) -> list:
        filters = []
        for field, value in criteria.model_dump(exclude_none=True).items():
            filters.append(getattr(User, field) == value)
        return filters

    @staticmethod
    def _to_naive_utc_datetime(value: str) -> datetime:
        """Parse ISO datetime text and normalize to naive UTC for DB writes."""
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    async def create(self, data: User, tx: Optional[DBTransaction] = None) -> UUID:
        try:
            if tx is not None:
                await tx.add(data)
                await tx.flush()
                self._logger.debug(f"New user created: {data.id}")
                return data.id

            async with self._db.get_session() as session:
                session.add(data)
                await session.flush()
                self._logger.debug(f"New user created: {data.id}")
                return data.id

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while creating a new user.",
                error_code="USER_CREATION_ERROR",
                stack_trace=str(e),
            )

    async def get_by_id(
        self, user_id: UUID, tx: Optional[DBTransaction] = None
    ) -> Optional[User]:
        try:
            stmt = select(User).where(User.id == user_id)

            if tx is not None:
                result = await tx.execute(stmt)
                user = result.scalar_one_or_none()
                if user:
                    self._logger.debug(f"Found user: {user_id}")
                return user

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                if user:
                    self._logger.debug(f"Found user: {user_id}")
                return user

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while getting user by id.",
                error_code="USER_GET_ERROR",
                stack_trace=str(e),
            )

    async def update(
        self,
        user_id: UUID,
        new_user_data: UpdatedUserData,
        tx: Optional[DBTransaction] = None,
    ) -> Optional[User]:
        try:
            stmt = select(User).where(User.id == user_id)

            if tx is not None:
                result = await tx.execute(stmt)
                existing = result.scalar_one_or_none()

                if not existing:
                    return None

                if (
                    hasattr(new_user_data, "last_seen_at")
                    and new_user_data.last_seen_at is not None
                ):
                    existing.last_seen_at = self._to_naive_utc_datetime(
                        new_user_data.last_seen_at
                    )

                await tx.flush()
                self._logger.debug(f"User updated: {user_id}")
                return existing

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if not existing:
                    return None

                if (
                    hasattr(new_user_data, "last_seen_at")
                    and new_user_data.last_seen_at is not None
                ):
                    existing.last_seen_at = self._to_naive_utc_datetime(
                        new_user_data.last_seen_at
                    )

                await session.flush()
                self._logger.debug(f"User updated: {user_id}")
                return existing

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while updating user.",
                error_code="USER_UPDATE_ERROR",
                stack_trace=str(e),
            )

    async def delete(
        self, user_id: UUID, tx: Optional[DBTransaction] = None
    ) -> bool:
        try:
            stmt = delete(User).where(User.id == user_id)

            if tx is not None:
                result = await tx.execute(stmt)
                deleted = (result.rowcount or 0) > 0
                if deleted:
                    self._logger.debug(f"User deleted: {user_id}")
                return deleted

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                deleted = (result.rowcount or 0) > 0
                if deleted:
                    self._logger.debug(f"User deleted: {user_id}")
                return deleted

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting user.",
                error_code="USER_DELETE_ERROR",
                stack_trace=str(e),
            )

    async def exists(
        self, user_id: UUID, tx: Optional[DBTransaction] = None
    ) -> bool:
        try:
            stmt = select(func.count()).select_from(User).where(User.id == user_id)

            if tx is not None:
                result = await tx.execute(stmt)
                return result.scalar_one() > 0

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return result.scalar_one() > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while checking if user exists.",
                error_code="USER_EXISTS_ERROR",
                stack_trace=str(e),
            )


