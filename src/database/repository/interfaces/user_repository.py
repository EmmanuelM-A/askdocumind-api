"""
Repository interface for user CRUD operations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from src.database.models import User
from src.database.repository.interfaces.db_transaction import DBTransaction


class UserSearchCriteria(BaseModel):
    """Criteria for filtering users in list/search operations."""

    id: Optional[UUID] = None
    last_seen_at_lte: Optional[datetime] = None


class UpdatedUserData(BaseModel):
    """Schema for updating user fields."""

    last_seen_at: Optional[str] = None


class UserRepositoryInterface(ABC):
    """
    Abstract interface for user repository operations.

    Defines the contract for all user-related database operations.
    Concrete implementations must implement all abstract methods.
    """

    @abstractmethod
    async def create(self, data: User, tx: Optional[DBTransaction] = None) -> UUID:
        """
        Create and persist a new user entity.

        :param data: The User entity to persist.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The UUID of the newly created user.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(
        self, user_id: UUID, tx: Optional[DBTransaction] = None
    ) -> Optional[User]:
        """
        Retrieve a single user by its unique identifier.

        :param user_id: The UUID of the user to retrieve.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The User entity if found, None otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def update(
        self,
        user_id: UUID,
        new_user_data: UpdatedUserData,
        tx: Optional[DBTransaction] = None,
    ) -> Optional[User]:
        """
        Update an existing user with new data.

        :param user_id: The UUID of the user to update.
        :param new_user_data: The update payload containing new field values.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The updated User entity if found, None otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, user_id: UUID, tx: Optional[DBTransaction] = None) -> bool:
        """
        Delete a user by its unique identifier.

        :param user_id: The UUID of the user to delete.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: True if user was deleted, False if not found.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete_many(self, user_ids: list[UUID], tx: Optional[DBTransaction] = None) -> int:
        """
        Delete multiple users by their unique identifiers.

        :param user_ids: List of UUIDs of the users to delete.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: Number of users deleted.
        """
        raise NotImplementedError


    @abstractmethod
    async def exists(self, user_id: UUID, tx: Optional[DBTransaction] = None) -> bool:
        """
        Check if a user with the given UUID exists.

        :param user_id: The UUID to check for existence.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: True if user exists, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete_by_criteria(
        self,
        criteria: UserSearchCriteria,
        tx: Optional[DBTransaction] = None,
    ) -> int:
        """
        Delete users that match the provided criteria.

        :param criteria: Predicate criteria used to target users for deletion.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: Number of users deleted.
        """
        raise NotImplementedError

    @abstractmethod
    async def update_last_seen(
        self, user_id: UUID, tx: Optional[DBTransaction] = None
    ) -> None:
        """
        Update the last seen timestamp of a user to the current time.

        :param user_id: The UUID of the user to update.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: None
        """
        raise NotImplementedError

    @abstractmethod
    async def get_all_expired_user_ids(
        self, cutoff: datetime, tx: Optional[DBTransaction] = None
    ) -> list[UUID]:
        """
        Retrieve all user IDs that have a last_seen_at timestamp older than the cutoff.
        
        :param cutoff: The datetime threshold for determining expiration.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: List of UUIDs for expired users.
        """
        raise NotImplementedError
