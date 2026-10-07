from datetime import datetime
from abc import ABC, abstractmethod
from uuid import UUID

from src.auth.models.user import User
from src.database import DBTransaction


class UserRepository(ABC):
    """
    Abstract interface for user repository operations.

    Defines the contract for all user-related database operations.
    Concrete implementations must implement all abstract methods.
    """

    @abstractmethod
    async def create(self, data: User, tx: DBTransaction | None = None) -> User:
        """
        Create and persist a new user entity.
        """
        raise NotImplementedError("Method 'create' not implemented in subclass")

    @abstractmethod
    async def get_by_id(
        self, user_id: UUID, tx: DBTransaction | None = None
    ) -> User | None:
        """
        Retrieve a single user by its unique identifier.
        """
        raise NotImplementedError("Method 'get_by_id' not implemented in subclass")

    @abstractmethod
    async def delete(self, user_id: UUID, tx: DBTransaction | None = None) -> bool:
        """
        Delete a user by its unique identifier.
        """
        raise NotImplementedError("Method 'delete' not implemented in subclass")

    @abstractmethod
    async def delete_many(
        self, user_ids: list[UUID], tx: DBTransaction | None = None
    ) -> int:
        """
        Delete multiple users by their unique identifiers.
        """
        raise NotImplementedError("Method 'delete_many' not implemented in subclass")

    @abstractmethod
    async def update_last_seen(
        self, user_id: UUID, tx: DBTransaction | None = None
    ) -> None:
        """
        Update the last seen timestamp of a user to the current time.
        """
        raise NotImplementedError(
            "Method 'update_last_seen' not implemented in subclass"
        )

    @abstractmethod
    async def get_expired_users(
        self, cutoff: datetime, tx: DBTransaction | None = None
    ) -> list[UUID]:
        """
        Retrieve all user IDs that have a last_seen_at timestamp older than
        the cutoff.
        """
        raise NotImplementedError(
            "Method 'get_expired_users' not implemented in subclass"
        )
