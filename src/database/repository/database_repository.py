"""
Repository abstractions for database entities.

This module defines a generic `DatabaseRepository` abstract base class that
establishes a minimal CRUD contract for repository implementations. It also
provides explicit subclasses for common domain repositories used across the
project.
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Optional, Type, List
from uuid import UUID

from sqlalchemy import delete

from src.database.connection import get_database_connection
from src.database.models import Base

# Type variable for the model
T = TypeVar("T", bound=Base)


class DatabaseRepository(ABC, Generic[T]):
    """
    Abstract base class defining a repository contract for entity type `T`.

    Methods:
    - create: persist a new entity and return a representation (usually a dict).
    - get: retrieve an entity by its identifier or all entities when no id is
      provided.
    - update: apply changes to an existing entity and return a representation.
    - delete: remove an entity and return an identifier or confirmation.
    - exists: check whether an entity with the given id exists.

    Concrete implementations must implement all abstract methods.
    """

    def __init__(self, model: Optional[Type[T]] = None):
        """
        Initialize the repository.

        :param model: Optional mapped model/class associated with this repository.
        """
        self._db = get_database_connection()
        self._model = model

    @property
    def get_db_connection(self):
        """
        Access the database connection instance.

        :return: The database connection object.
        """
        return self._db

    @abstractmethod
    async def create(self, entity: T) -> UUID:
        """
        Persist `entity_data` and return a dictionary representing the created entity.

        :param entity: The entity payload to create.
        :return: The unique identifier of the created entity.
        """
        raise NotImplementedError

    @abstractmethod
    async def get(self, entity_id: Optional[UUID] = None) -> Optional[T] | List[T]:
        """
        Retrieve an entity by its identifier, or return all entities when no
        identifier is provided.

        :param entity_id: Optional UUID of the entity to retrieve. If None,
                          implementations should return a list of all entities.
        :return: The entity object corresponding to `entity_id`, or a list of
                 entities when `entity_id` is None.
        """
        raise NotImplementedError

    @abstractmethod
    async def update(self, entity_id: UUID, new_entity_data: T) -> Optional[T]:
        """
        Update an existing entity with `new_entity_data`.

        :param entity_id: The unique identifier of the entity to update.
        :param new_entity_data: The new entity data to apply.
        :return: Dictionary representation of the updated entity.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, entity_id: UUID) -> UUID:
        """
        Delete the entity identified by `entity_id`.

        :param entity_id: The unique identifier of the entity to delete.
        :return: Confirmation string or the identifier of the deleted entity.
        """
        raise NotImplementedError

    @abstractmethod
    async def exists(self, entity_id: UUID) -> bool:
        """
        Check whether an entity with `entity_id` exists.

        :param entity_id: The unique identifier to check for existence.
        :return: True if the entity exists, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def count(self, filter_id: Optional[UUID]) -> int:
        """
        Count entities matching the given filter.

        :param filter_id: The filter criteria to count entities.
        :return: The count of entities matching the filter.
        """
        raise NotImplementedError

    async def create_many(self, entities: List[T]) -> List[UUID]:
        """
        Persist multiple entities (model instances) in a single transactional operation.

        The operation is all-or-nothing: if any error occurs the transaction will
        roll back.

        :param entities: List of model instances to create.
        :return: List of UUIDs for created rows.
        """

        if not entities:
            return []

        async with self._db.get_session() as session:
            # Ensure transactional behaviour: commit on success, rollback on error
            async with session.begin():
                # Add all model instances and flush to populate their IDs
                session.add_all(entities)
                await session.flush()

                return [e.id for e in entities]

    async def delete_many(self, entity_ids: list[UUID]) -> int:
        """
        Delete multiple entities and return the number of deleted entities.

        :param entity_ids: List of unique identifiers of entities to delete.
        :return: The number of entities deleted.
        """

        if self._model is None:
            raise NotImplementedError("delete_many requires repository model")

        async with self._db.get_session() as session:
            result = await session.execute(
                delete(self._model).where(self._model.id.in_(entity_ids))
            )
            return result.rowcount
