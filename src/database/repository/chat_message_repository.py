"""
Responsible for managing chat message data access in the database.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select, func, delete
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from src.config.constants import ChatMessageRole
from src.database.models import ChatMessage

from src.database.repository.database_repository import DatabaseRepository


class ChatMessageSearchCriteria(BaseModel):
    id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    role: Optional[ChatMessageRole] = None


class ChatMessageRepository(DatabaseRepository[ChatMessage]):
    """
    Repository specialization for chat message entities.
    """

    async def create(self, entity: ChatMessage) -> UUID:
        """
        Create a new chat message entry in the database.

        :param entity: ChatMessage entity to create.
        :return: A dictionary containing the creation confirmation results.

        :raises SQLAlchemyError: If a database error occurs during creation.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """

        try:
            async with self._db.get_session() as session:
                session.add(entity)
                await session.flush()  # ensures ID is generated
                self._logger.debug(f"New chat message entry created: {entity.id}")
                return entity.id

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def list_by(
        self, criteria: Optional[ChatMessageSearchCriteria] = None
    ) -> List[ChatMessage]:
        """
        Retrieve chat messages matching the given criteria.

        If no criteria is provided, all chat messages are returned.
        """
        try:
            async with self._db.get_session() as session:
                stmt = select(ChatMessage)

                if criteria is None:
                    result = await session.execute(stmt)
                    self._logger.debug(
                        "No criteria provided, returning all chat messages"
                    )
                    return result.scalars().all()

                filters = []

                for field, value in criteria.model_dump(exclude_none=True).items():
                    filters.append(getattr(ChatMessage, field) == value)

                stmt = stmt.where(*filters)
                result = await session.execute(stmt)
                self._logger.debug("Found chat messages matching criteria")
                return result.scalars().all()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def get_by_id(self, entity_id: UUID) -> Optional[ChatMessage]:
        """
        Retrieve a chat message entry by its ID.

        :param entity_id: The ID of the chat message to retrieve.
        :return: The ChatMessage entity if found, None otherwise.

        :raise SQLAlchemyError: If a database error occurs during retrieval.
        :raise IntegrityError: If a data integrity violation occurs.
        :raise Exception: For any other exceptions that may arise.
        """

        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    select(ChatMessage).where(ChatMessage.id == entity_id)
                )
                chat_message = result.scalar_one_or_none()
                if chat_message:
                    self._logger.debug(
                        "Found chat message entry matching the provided ID"
                    )
                return chat_message

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def get_by_criteria(
        self, criteria: ChatMessageSearchCriteria
    ) -> Optional[ChatMessage]:
        """
        Retrieve a single chat message matching the given criteria.
        """
        try:
            filters = []

            for field, value in criteria.model_dump(exclude_none=True).items():
                filters.append(getattr(ChatMessage, field) == value)

            if not filters:
                self._logger.debug("No chat messages matching criteria")
                return None

            async with self._db.get_session() as session:
                result = await session.execute(select(ChatMessage).where(*filters))
                self._logger.debug("Found chat messages matching criteria")
                return result.scalars().first()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def update(
        self, entity_id: UUID, new_entity_data: ChatMessage
    ) -> Optional[ChatMessage]:
        self._logger.info("Chat message cannot be updated!")
        return None

    async def delete(self, entity_id: UUID) -> bool:
        """
        Delete a chat message by its ID.

        :param entity_id: The ID of the chat message to delete.
        :return: The identifier of the deleted entity.

        :raise SQLAlchemyError: If a database error occurs during deletion.
        :raise IntegrityError: If a data integrity violation occurs.
        :raise Exception: For any other exceptions that may arise.
        """

        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    delete(ChatMessage).where(ChatMessage.id == entity_id)
                )
                return result.rowcount > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def exists(self, entity_id: UUID) -> bool:
        """
        Check if a chat message exists.

        :param entity_id: The ID of the chat message to check.
        :return: True if exists, False otherwise.

        :raise SQLAlchemyError: If a database error occurs during deletion.
        :raise IntegrityError: If a data integrity violation occurs.
        :raise Exception: For any other exceptions that may arise.
        """

        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.id == entity_id)
                )
                return result.scalar_one() > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def count(self, filter_id: Optional[UUID]) -> int:
        """
        Count total chat messages, optionally filtered by chat session ID.

        :param filter_id: Optional chat session ID to filter messages.
        :return: Total count of chat messages.

        :raise SQLAlchemyError: If a database error occurs during counting.
        :raise IntegrityError: If a data integrity violation occurs.
        :raise Exception: For any other exceptions that may arise.
        """

        try:
            async with self._db.get_session() as session:
                stmt = select(func.count()).select_from(ChatMessage)
                if filter_id:
                    stmt = stmt.where(ChatMessage.session_id == filter_id)
                result = await session.execute(stmt)
                return result.scalar_one()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e
