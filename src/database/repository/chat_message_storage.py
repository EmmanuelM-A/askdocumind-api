"""
Responsible for managing chat message storage in the remote database.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, delete

from src.database.connection import get_database_connection
from src.database.models import ChatMessage
from src.database.storage.storage_base import StorageBase
from src.errors.custom_exceptions import throw_database_error


class RemoteChatMessageStorage(StorageBase[ChatMessage]):
    """
    Remote storage implementation for chat messages using the database
    connection service.
    """

    def __init__(self):
        self.db = get_database_connection()

    async def create(self, entity: ChatMessage) -> Optional[str]:
        """Create a new chat message entry in the database."""

        try:
            async with self.db.get_session() as session:
                session.add(entity)
                await session.flush()  # ensures ID is generated
                return str(entity.id)

        except Exception as e:
            throw_database_error(
                message="Failed to create chat message.",
                error_code="CREATE_CHAT_MESSAGE_ENTRY_FAILED",
                stack_trace=str(e),
            )
            return None

    async def get(self, entity_id: str) -> Optional[ChatMessage]:
        """Retrieve a chat message by its ID."""

        try:
            async with self.db.get_session() as session:
                result = await session.execute(
                    select(ChatMessage).where(ChatMessage.id == UUID(entity_id))
                )
                return result.scalar_one_or_none()

        except Exception as e:
            throw_database_error(
                message="Failed to retrieve chat message.",
                error_code="GET_CHAT_MESSAGE_ENTRY_FAILED",
                stack_trace=str(e),
            )
            return None

    async def update(
        self, entity_id: str, entity: ChatMessage
    ) -> Optional[ChatMessage]:
        """Update an existing chat message."""

        try:
            async with self.db.get_session() as session:
                result = await session.execute(
                    select(ChatMessage).where(ChatMessage.id == UUID(entity_id))
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    return None

                existing.content = entity.content
                existing.role = entity.role

                await session.flush()
                return existing

        except Exception as e:
            throw_database_error(
                message="Failed to update chat message.",
                error_code="CHAT_MESSAGE_UPDATE_FAILED",
                stack_trace=str(e),
            )
            return None

    async def delete(self, entity_id: str) -> bool:
        """Delete a chat message by its ID."""

        try:
            async with self.db.get_session() as session:
                result = await session.execute(
                    delete(ChatMessage).where(ChatMessage.id == UUID(entity_id))
                )
                return result.rowcount > 0

        except Exception as e:
            throw_database_error(
                message="Failed to delete chat message.",
                error_code="CHAT_MESSAGE_DELETE_FAILED",
                stack_trace=str(e),
            )
            return False

    async def exists(self, entity_id: str) -> bool:
        """Check if a chat message exists."""

        try:
            async with self.db.get_session() as session:
                result = await session.execute(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.id == UUID(entity_id))
                )
                return result.scalar_one() > 0

        except Exception as e:
            throw_database_error(
                message="Failed to check chat message existence.",
                error_code="CHAT_MESSAGE_EXISTS_FAILED",
                stack_trace=str(e),
            )
            return False

    async def count(self, owner_id: Optional[str] = None) -> int:
        """
        Count total chat messages that belong to a specific chat session. If
        no chat session ID is provided, counts all chat messages.

        :param owner_id: The chat session ID to filter messages by (optional).
        :return: Total count of chat messages.
        """

        try:
            async with self.db.get_session() as session:
                stmt = select(func.count()).select_from(ChatMessage)
                if owner_id:
                    stmt = stmt.where(ChatMessage.session_id == UUID(owner_id))
                result = await session.execute(stmt)
                return result.scalar_one()

        except Exception as e:
            throw_database_error(
                message="Failed to count chat messages.",
                error_code="CHAT_MESSAGE_COUNT_FAILED",
                stack_trace=str(e),
            )
            return 0
