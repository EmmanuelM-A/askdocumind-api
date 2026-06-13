"""
Concrete implementation of the user repository, providing methods for CRUD
operations and specific queries related to user entities.
"""

from typing import Optional, cast
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

        if criteria.id is not None:
            filters.append(User.id == criteria.id)

        if criteria.last_seen_at_lte is not None:
            filters.append(User.last_seen_at <= criteria.last_seen_at_lte)

        return filters

    async def create(self, data: User, tx: Optional[DBTransaction] = None) -> UUID:
        try:
            if tx is not None:
                await tx.add(data)
                await tx.flush()
                self._logger.debug(f"New user created: {data.id}")
                return cast(UUID, data.id)

            async with self._db.get_session() as session:
                session.add(data)
                await session.flush()
                self._logger.debug(f"New user created: {data.id}")
                return cast(UUID, data.id)

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
                    existing.last_seen_at = new_user_data.last_seen_at

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
                    existing.last_seen_at = new_user_data.last_seen_at

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

    async def delete_many(
        self, user_ids: list[UUID], tx: Optional[DBTransaction] = None
    ) -> int:
        if not user_ids:
            return 0

        try:
            stmt = delete(User).where(User.id.in_(user_ids))

            if tx is not None:
                result = await tx.execute(stmt)
                deleted_count = result.rowcount or 0
                self._logger.debug(f"Deleted {deleted_count} user(s) in bulk.")
                return deleted_count

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                deleted_count = result.rowcount or 0
                self._logger.debug(f"Deleted {deleted_count} user(s) in bulk.")
                return deleted_count

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting multiple users.",
                error_code="USER_BULK_DELETE_ERROR",
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

    async def delete_by_criteria(
        self,
        criteria: UserSearchCriteria,
        tx: Optional[DBTransaction] = None,
    ) -> int:
        try:
            filters = self._build_filters(criteria)

            if not filters:
                self._logger.warning(
                    "Skipping user delete_by_criteria because no filter criteria were provided."
                )
                return 0

            stmt = delete(User).where(*filters)

            if tx is not None:
                result = await tx.execute(stmt)
                deleted_count = result.rowcount or 0
                if deleted_count > 0:
                    self._logger.debug(
                        f"Deleted {deleted_count} user(s) matching criteria."
                    )
                return deleted_count

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                deleted_count = result.rowcount or 0
                if deleted_count > 0:
                    self._logger.debug(
                        f"Deleted {deleted_count} user(s) matching criteria."
                    )
                return deleted_count

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting users by criteria.",
                error_code="USER_DELETE_BY_CRITERIA_ERROR",
                stack_trace=str(e),
            )
    

    async def update_last_seen(self, user_id: UUID, tx: Optional[DBTransaction] = None) -> None:
        """Update the last_seen_at timestamp of a user to the current UTC time."""
        try:
            stmt = select(User).where(User.id == user_id)

            if tx is not None:
                result = await tx.execute(stmt)
                existing = result.scalar_one_or_none()
                if not existing:
                    self._logger.warning(f"User {user_id} not found for last seen update.")
                    return
                existing.last_seen_at = datetime.now(timezone.utc)
                await tx.flush()
                self._logger.debug(f"Updated last seen for user: {user_id}")
                return

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if not existing:
                    self._logger.warning(f"User {user_id} not found for last seen update.")
                    return
                existing.last_seen_at = datetime.now(timezone.utc)
                await session.flush()
                self._logger.debug(f"Updated last seen for user: {user_id}")

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while updating the user's last seen timestamp.",
                error_code="USER_UPDATE_LAST_SEEN_ERROR",
                stack_trace=str(e),
            )

    async def get_all_expired_user_ids(
        self, cutoff: datetime, tx: Optional[DBTransaction] = None
    ) -> list[UUID]:
        try:
            stmt = select(User.id).where(
                User.last_seen_at.is_not(None),
                User.last_seen_at <= cutoff,
            )

            if tx is not None:
                result = await tx.execute(stmt)
                return list(result.scalars().all())

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return list(result.scalars().all())

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while fetching expired user IDs.",
                error_code="USER_GET_EXPIRED_IDS_ERROR",
                stack_trace=str(e),
            )

