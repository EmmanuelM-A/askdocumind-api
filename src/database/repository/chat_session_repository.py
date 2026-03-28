"""
Responsible for managing chat session storage in the remote database.
"""

from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.database.models import ChatSession
from src.database.repository.database_repository import DatabaseRepository


class ChatSessionSearchCriteria(BaseModel):
    id: Optional[UUID] = None
    title: Optional[str] = None
    total_messages: Optional[int] = None


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
                self._logger.debug(f"New chat session created: {entity.id}")
                return entity.id

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def list_by(
        self, criteria: Optional[ChatSessionSearchCriteria] = None
    ) -> List[ChatSession]:
        """
        Retrieve chat sessions matching the given criteria.

        If no criteria is provided, all chat sessions are returned.
        """
        try:
            async with self._db.get_session() as session:
                stmt = select(ChatSession)

                if criteria is None:
                    result = await session.execute(stmt)
                    self._logger.debug("No criteria provided, returning all chat sessions")
                    return result.scalars().all()

                filters = []

                for field, value in criteria.model_dump(exclude_none=True).items():
                    filters.append(getattr(ChatSession, field) == value)

                stmt = stmt.where(*filters)
                result = await session.execute(stmt)
                self._logger.debug("Found chat sessions matching criteria")
                return result.scalars().all()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

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
                chat_session = result.scalar_one_or_none()
                if chat_session:
                    self._logger.debug(f"Found chat session: {entity_id}")
                return chat_session

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def get_by_criteria(self, criteria: ChatSessionSearchCriteria) -> Optional[ChatSession]:
        """
        Retrieve a single chat session matching the given criteria.
        """
        try:
            filters = []

            for field, value in criteria.model_dump(exclude_none=True).items():
                filters.append(getattr(ChatSession, field) == value)

            if not filters:
                self._logger.debug("No criteria provided for get_by_criteria")
                return None

            async with self._db.get_session() as session:
                result = await session.execute(select(ChatSession).where(*filters))
                self._logger.debug("Found chat session matching criteria")
                return result.scalars().first()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

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
        Count chat sessions, optionally filtered by chat session ID.

        :param filter_id: Optional chat session ID to filter by.
        :return: Total count of chat sessions.

        :raises SQLAlchemyError: If a database error occurs during counting.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """
        try:
            async with self._db.get_session() as session:
                stmt = select(func.count()).select_from(ChatSession)
                if filter_id:
                    stmt = stmt.where(ChatSession.id == filter_id)
                result = await session.execute(stmt)
                return result.scalar_one()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e
