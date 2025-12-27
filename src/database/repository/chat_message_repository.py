"""
Responsible for managing chat message data access in the database.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, delete
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from src.database.models import ChatMessage

from src.database.repository.database_repository import DatabaseRepository


class ChatMessageRepository(DatabaseRepository[ChatMessage]):
    """
    Repository specialization for chat message entities.
    """

    async def create(self, entity: ChatMessage) -> str:
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
                return str(entity.id)

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def get(self, entity_id: str) -> Optional[ChatMessage]:
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
                    select(ChatMessage).where(ChatMessage.id == UUID(entity_id))
                )
                return result.scalar_one_or_none()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def update(
        self, entity_id: str, new_entity_data: ChatMessage
    ) -> Optional[ChatMessage]:
        """
        Update an existing chat message.

        :param entity_id: The ID of the chat message to update.
        :param new_entity_data: The new chat message data to apply.
        :return: The updated ChatMessage entity if successful, None if not found.

        :raise SQLAlchemyError: If a database error occurs during update.
        :raise IntegrityError: If a data integrity violation occurs.
        :raise Exception: For any other exceptions that may arise.
        """

        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    select(ChatMessage).where(ChatMessage.id == UUID(entity_id))
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    return None

                existing.content = new_entity_data.content
                existing.role = new_entity_data.role

                await session.flush()
                return existing

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def delete(self, entity_id: str) -> str:
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
                    delete(ChatMessage).where(ChatMessage.id == UUID(entity_id))
                )
                return result.rowcount > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def exists(self, entity_id: str) -> bool:
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
                    .where(ChatMessage.id == UUID(entity_id))
                )
                return result.scalar_one() > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def count(self, filter_id: Optional[str]) -> int:
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
                    stmt = stmt.where(ChatMessage.session_id == UUID(filter_id))
                result = await session.execute(stmt)
                return result.scalar_one()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e
