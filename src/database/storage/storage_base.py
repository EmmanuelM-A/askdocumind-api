"""
Abstract base class to store uploaded entities.
"""

from abc import ABC, abstractmethod
from typing import Optional, Generic, TypeVar

# Generic type for entities stored
T = TypeVar("T")


class StorageBase(ABC, Generic[T]):
    """
    Abstract base class for all data access implementations.

    Defines the contract that all storage systems must implement.
    Supports CRUD operations and bulk queries.
    """

    @abstractmethod
    async def create(self, entity: T) -> Optional[str]:
        """
        Create a new entity in storage.

        Args:
            entity: The entity to store

        Returns:
            The ID of the created entity

        Raises:
            ApiException: If creation fails
        """
        raise NotImplementedError("Subclasses must implement create()")

    @abstractmethod
    async def get(self, entity_id: str) -> Optional[T]:
        """
        Retrieve an entity by ID.

        Args:
            entity_id: The unique identifier

        Returns:
            The entity if found, None otherwise
        """
        raise NotImplementedError("Subclasses must implement get()")

    @abstractmethod
    async def update(self, entity_id: str, entity: T) -> Optional[T]:
        """
        Update an existing entity.

        Args:
            entity_id: The unique identifier
            entity: The updated entity data

        Returns:
            The updated entity if successful, None if not found

        Raises:
            StorageException: If update fails
        """
        raise NotImplementedError("Subclasses must implement update()")

    @abstractmethod
    async def delete(self, entity_id: str) -> bool:
        """
        Delete an entity by ID.

        Args:
            entity_id: The unique identifier

        Returns:
            True if deleted, False if not found
        """
        raise NotImplementedError("Subclasses must implement delete()")

    @abstractmethod
    async def exists(self, entity_id: str) -> bool:
        """
        Check if an entity exists.

        Args:
            entity_id: The unique identifier

        Returns:
            True if exists, False otherwise
        """
        raise NotImplementedError("Subclasses must implement exists()")

    async def count(self, owner_id: Optional[str] = None) -> int:
        """
        Count total entities in storage that belong to a specific owner.
        If owner is None, count all entities.

        Args:
            owner_id: Optional owner identifier to filter by

        Returns:
            Total count of entities
        """
        raise NotImplementedError("Subclasses must implement count()")


# Storing entities like uploaded files


class StorageService(ABC):

    def save(self):
        pass

    def load(self):
        pass

    def delete(self):
        pass

    def exists(self):
        pass


class LocalFileStorageService(StorageService):  # EXAMPLE

    def update(self):
        pass

    def count(self):
        pass


class S3StorageService(StorageService):  # EXAMPLE
    pass


# Database operations/repositories


class BaseRepository(ABC):

    def create(self, entity_data):
        pass

    def get(self, entity_id):
        pass

    def update(self, entity_id, new_entity_data):
        pass

    def delete(self, entity_id):
        pass

    def exists(self, entity_id):
        pass


class DocumentRepository(BaseRepository):
    pass


class ChatMessageRepository(BaseRepository):
    pass


class ChatSessionRepository(BaseRepository):
    pass
