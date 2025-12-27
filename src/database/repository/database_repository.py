"""
Repository abstractions for database entities.

This module defines a generic `DatabaseRepository` abstract base class that
establishes a minimal CRUD contract for repository implementations. It also
provides explicit subclasses for common domain repositories used across the
project.

Implementations should inherit from `DatabaseRepository[T]` and implement all
abstract methods to interact with the underlying persistence layer.
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Optional

from src.database.connection import get_database_connection

T = TypeVar("T")


class DatabaseRepository(ABC, Generic[T]):
    """
    Abstract base class defining a repository contract for entity type `T`.

    Methods:
    - create: persist a new entity and return a representation (usually a dict).
    - get: retrieve an entity by its identifier.
    - update: apply changes to an existing entity and return a representation.
    - delete: remove an entity and return an identifier or confirmation.
    - exists: check whether an entity with the given id exists.

    Concrete implementations must implement all abstract methods.
    """

    def __init__(self):
        self._db = get_database_connection()

    @property
    def get_db_connection(self):
        """
        Access the database connection instance.

        :return: The database connection object.
        """
        return self._db

    @abstractmethod
    async def create(self, entity_data: T) -> str:
        """
        Persist `entity_data` and return a dictionary representing the created entity.

        :param entity_data: The entity payload to create.
        :return: Dictionary representation of the created entity (may include generated id).
        """
        raise NotImplementedError

    @abstractmethod
    async def get(self, entity_id: str) -> Optional[T]:
        """
        Retrieve an entity by its identifier.

        :param entity_id: The unique identifier of the entity to retrieve.
        :return: The entity object corresponding to `entity_id`.
        """
        raise NotImplementedError

    @abstractmethod
    async def update(self, entity_id: str, new_entity_data: T) -> Optional[T]:
        """
        Update an existing entity with `new_entity_data`.

        :param entity_id: The unique identifier of the entity to update.
        :param new_entity_data: The new entity data to apply.
        :return: Dictionary representation of the updated entity.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, entity_id: str) -> str:
        """
        Delete the entity identified by `entity_id`.

        :param entity_id: The unique identifier of the entity to delete.
        :return: Confirmation string or the identifier of the deleted entity.
        """
        raise NotImplementedError

    @abstractmethod
    async def exists(self, entity_id: str) -> bool:
        """
        Check whether an entity with `entity_id` exists.

        :param entity_id: The unique identifier to check for existence.
        :return: True if the entity exists, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def count(self, filter_id: Optional[str]) -> int:
        """
        Count entities matching the given filter.

        :param filter_id: The filter criteria to count entities.
        :return: The count of entities matching the filter.
        """
        raise NotImplementedError
