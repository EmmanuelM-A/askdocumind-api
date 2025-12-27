"""
Responsible for managing chat session storage in the remote database.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, delete

from src.database.connection import get_database_connection
from src.database.models import ChatSession
from src.database.storage.storage_base import StorageBase
from src.errors.custom_exceptions import throw_database_error


class RemoteChatSessionStorage(StorageBase[ChatSession]):
    """
    Remote storage implementation for chat sessions using database connection
    service.
    """

    def __init__(self):
        self.db = get_database_connection()

    async def create(self, entity: ChatSession) -> Optional[str]:
        """
        Creates a new chat session entry in the database.

        :param entity: ChatSession entity to create.
        :return: The ID of the created chat session.
        """

        try:
            async with self.db.get_session() as session:
                session.add(entity)
                await session.flush()
                return str(entity.id)

        except Exception as e:
            throw_database_error(
                message="Failed to create chat session.",
                error_code="CHAT_SESSION_CREATE_FAILED",
                stack_trace=str(e),
            )
            return None

    async def get(self, entity_id: str) -> Optional[ChatSession]:
        """
        Retrieve a chat session by its ID.

        :param entity_id: The ID of the chat session to retrieve.
        :return: The ChatSession entity if found and None otherwise.

        :raises ApiException: If retrieval fails.
        """
        try:
            async with self.db.get_session() as session:
                result = await session.execute(
                    select(ChatSession).where(ChatSession.id == UUID(entity_id))
                )
                return result.scalar_one_or_none()

        except Exception as e:
            throw_database_error(
                message="Failed to retrieve chat session.",
                error_code="CHAT_SESSION_GET_FAILED",
                stack_trace=str(e),
            )
            return None

    async def update(
        self, entity_id: str, entity: ChatSession
    ) -> Optional[ChatSession]:
        """
        Update an existing chat session based on provided entity data.

        :param entity_id: The ID of the chat session to update.
        :param entity: The ChatSession entity with updated data.
        :return: The updated ChatSession entity if successful, None if not found.

        :raises ApiException: If update fails.
        """
        try:
            async with self.db.get_session() as session:
                result = await session.execute(
                    select(ChatSession).where(ChatSession.id == UUID(entity_id))
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    return None

                # Update allowed fields only
                if hasattr(entity, "title"):
                    existing.title = entity.title

                await session.flush()
                return existing

        except Exception as e:
            throw_database_error(
                message="Failed to update chat session.",
                error_code="CHAT_SESSION_UPDATE_FAILED",
                stack_trace=str(e),
            )
            return None

    async def delete(self, entity_id: str) -> bool:
        """
        Delete a chat session by its ID.

        :param entity_id: The ID of the chat session to delete.
        :return: True if deleted, False if not found.

        :raises ApiException: If deletion fails.
        """
        try:
            async with self.db.get_session() as session:
                result = await session.execute(
                    delete(ChatSession).where(ChatSession.id == UUID(entity_id))
                )
                return result.rowcount > 0

        except Exception as e:
            throw_database_error(
                message="Failed to delete chat session.",
                error_code="CHAT_SESSION_DELETE_FAILED",
                stack_trace=str(e),
            )
            return False

    async def exists(self, entity_id: str) -> bool:
        """
        Check if a chat session exists by its ID.

        :param entity_id: The ID of the chat session to check.
        :return: True if exists, False otherwise.

        :raises ApiException: If the existence check fails.
        """
        try:
            async with self.db.get_session() as session:
                result = await session.execute(
                    select(func.count())
                    .select_from(ChatSession)
                    .where(ChatSession.id == UUID(entity_id))
                )
                return result.scalar_one() > 0

        except Exception as e:
            throw_database_error(
                message="Failed to check chat session existence.",
                error_code="CHAT_SESSION_EXISTS_FAILED",
                stack_trace=str(e),
            )
            return False

    async def count(self, owner_id: Optional[str] = None) -> Optional[int]:
        """
        Count the total number of chat sessions that belong to a specific owner.
        If no owner ID is provided, counts all chat sessions.

        :param owner_id: The owner ID to filter chat sessions by (optional).
        :return: Total count of chat sessions.

        :raises ApiException: If counting fails.
        """
        try:
            async with self.db.get_session() as session:
                result = await session.execute(
                    select(func.count()).select_from(ChatSession)
                )
                return result.scalar_one()

        except Exception as e:
            throw_database_error(
                message="Failed to count chat sessions.",
                error_code="CHAT_SESSION_COUNT_FAILED",
                stack_trace=str(e),
            )
            return None
