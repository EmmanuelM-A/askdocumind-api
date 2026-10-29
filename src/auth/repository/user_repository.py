from abc import ABC, abstractmethod
from uuid import UUID

from src.auth.models.user import User


class UserRepository(ABC):
    """
    Abstract interface for user repository operations.

    Defines the contract for all user-related database operations.
    Concrete implementations must implement all abstract methods.
    """

    @abstractmethod
    async def create(self, data: User) -> User:
        """
        Create and persist a new user entity.
        """
        raise NotImplementedError("Method 'create' not implemented in subclass")

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> User | None:
        """
        Retrieve a single user by its unique identifier.
        """
        raise NotImplementedError("Method 'get_by_id' not implemented in subclass")

    @abstractmethod
    async def delete(self, user_id: UUID) -> bool:
        """
        Delete a user by its unique identifier.
        """
        raise NotImplementedError("Method 'delete' not implemented in subclass")

    @abstractmethod
    async def delete_many(self, user_ids: list[UUID]) -> int:
        """
        Delete multiple users by their unique identifiers.
        """
        raise NotImplementedError("Method 'delete_many' not implemented in subclass")

    @abstractmethod
    async def update_last_seen(self, user_id: UUID, freq_mins: int) -> None:
        """
        Update the last seen timestamp of a user to the current time, if and
        only if the last seen timestamp is older than the specified
        update frequency.
        """
        raise NotImplementedError(
            "Method 'update_last_seen' not implemented in subclass"
        )
