"""
Responsible for managing chat session storage in the remote database.
"""

from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.database.models import ChatSession
from src.database.repository.database_repository import DatabaseRepository


class ChatSessionRepository(DatabaseRepository[ChatSession]):
    """
    Repository specialization for chat session entities.
    """

    async def create(self, entity: ChatSession) -> UUID:
        """
        Creates a new chat session entry in the database.

        :param entity: ChatSession entity to create.
        :return: The ID of the created chat session.

        :raise SQLAlchemyError: If a database error occurs during update.
        :raise IntegrityError: If a data integrity violation occurs.
        :raise Exception: For any other exceptions that may arise.
        """

        try:
            async with self._db.get_session() as session:
                session.add(entity)
                await session.flush()
                return entity.id

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def list_by(
        self, criteria: Optional[ChatSession] = None
    ) -> List[ChatSession]:
        pass

    async def get_by_id(self, entity_id: UUID) -> Optional[ChatSession]:
        """
        Retrieve a chat session by its ID.

        :param entity_id: The ID of the chat session to retrieve.
        :return: The ChatSession entity if found and None otherwise.

        :raises SQLAlchemyError: If a database error occurs during retrieval.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """
        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    select(ChatSession).where(ChatSession.id == entity_id)
                )
                return result.scalar_one_or_none()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def get_by_criteria(self, criteria: ChatSession) -> Optional[ChatSession]:
        pass

    async def update(
        self, entity_id: UUID, new_entity_data: ChatSession
    ) -> Optional[ChatSession]:
        """
        Update an existing chat session based on provided entity data.

        :param entity_id: The ID of the chat session to update.
        :param new_entity_data: The new chat session data to apply.
        :return: The updated ChatSession entity if successful, None if not found.

        :raises SQLAlchemyError: If a database error occurs during update.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """
        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    select(ChatSession).where(ChatSession.id == entity_id)
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    return None

                # Update allowed fields only
                if hasattr(new_entity_data, "title"):
                    existing.title = new_entity_data.title

                await session.flush()
                return existing

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def delete(self, entity_id: UUID) -> bool:
        """
        Delete a chat session by its ID.

        :param entity_id: The ID of the chat session to delete.
        :return: True if deleted, False if not found.

        :raises SQLAlchemyError: If a database error occurs during deletion.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """
        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    delete(ChatSession).where(ChatSession.id == entity_id)
                )
                return result.rowcount > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def exists(self, entity_id: UUID) -> bool:
        """
        Check if a chat session exists by its ID.

        :param entity_id: The ID of the chat session to check.
        :return: True if exists, False otherwise.

        :raises SQLAlchemyError: If a database error occurs during existence check.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """
        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    select(func.count())
                    .select_from(ChatSession)
                    .where(ChatSession.id == entity_id)
                )
                return result.scalar_one() > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def count(self, filter_id: Optional[UUID] = None) -> int:
        """
        Count the total number of chat sessions that belong to a specific owner.
        If no owner ID is provided, counts all chat sessions.

        :param filter_id: The owner ID to filter chat sessions by (optional).
        :return: Total count of chat sessions.

        :raises SQLAlchemyError: If a database error occurs during counting.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """
        try:
            async with self._db.get_session() as session:
                stmt = select(func.count()).select_from(ChatSession)
                if filter_id:
                    stmt = stmt.where(ChatSession.owner_id == filter_id)
                result = await session.execute(stmt)
                return result.scalar_one()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e
