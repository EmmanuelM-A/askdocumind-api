"""
Responsible for managing chat message data access in the database.
"""

from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, func, delete
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from src.database.connection import DatabaseConnection
from src.database.models import ChatMessage
from src.database.repository.interfaces.chat_message_repository import (
    ChatMessageRepositoryInterface,
    ChatMessageSearchCriteria,
    UpdatedChatMessageData,
)
from src.errors.custom_exceptions import database_error
from src.logger.base_logger import BaseLogger


class ChatMessageRepository(ChatMessageRepositoryInterface):
    """
    Concrete implementation of the chat message repository interface.
    """

    def __init__(self, connection: DatabaseConnection) -> None:
        self._db = connection
        self._logger = BaseLogger(__name__)

    async def create(self, entity: ChatMessage) -> UUID:
        try:
            async with self._db.get_session() as session:
                session.add(entity)
                await session.flush()  # ensures ID is generated
                self._logger.debug(f"New chat message entry created: {entity.id}")
                return entity.id

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while creating a new chat message.",
                error_code="CHAT_MESSAGE_CREATION_ERROR",
                stack_trace=str(e),
            )

    async def list_by(
        self, criteria: Optional[ChatMessageSearchCriteria] = None
    ) -> List[ChatMessage]:
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
            raise database_error(
                message="An error occurred while listing chat messages by criteria.",
                error_code="CHAT_MESSAGE_LISTING_ERROR",
                stack_trace=str(e),
            )

    async def get_by_id(self, entity_id: UUID) -> Optional[ChatMessage]:
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
            raise database_error(
                message="An error occurred while getting chat message by id.",
                error_code="CHAT_MESSAGE_GET_ERROR",
                stack_trace=str(e),
            )

    async def get_by_criteria(
        self, criteria: ChatMessageSearchCriteria
    ) -> Optional[ChatMessage]:
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
            raise database_error(
                message="An error occurred while getting chat message by criteria.",
                error_code="CHAT_MESSAGE_GET_ERROR",
                stack_trace=str(e),
            )

    async def update(
        self, entity_id: UUID, new_entity_data: UpdatedChatMessageData
    ) -> Optional[ChatMessage]:
        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    select(ChatMessage).where(ChatMessage.id == entity_id)
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    return None

                if (
                    hasattr(new_entity_data, "content")
                    and new_entity_data.content is not None
                ):
                    existing.content = new_entity_data.content
                if (
                    hasattr(new_entity_data, "role")
                    and new_entity_data.role is not None
                ):
                    existing.role = new_entity_data.role

                await session.flush()
                return existing

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while updating chat message.",
                error_code="CHAT_MESSAGE_UPDATE_ERROR",
                stack_trace=str(e),
            )

    async def delete(self, entity_id: UUID) -> bool:
        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    delete(ChatMessage).where(ChatMessage.id == entity_id)
                )
                return result.rowcount > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting chat message.",
                error_code="CHAT_MESSAGE_DELETE_ERROR",
                stack_trace=str(e),
            )

    async def exists(self, entity_id: UUID) -> bool:
        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.id == entity_id)
                )
                return result.scalar_one() > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while determining if chat message exists.",
                error_code="CHAT_MESSAGE_EXISTS_ERROR",
                stack_trace=str(e),
            )

    async def count(self, filter_id: Optional[UUID] = None) -> int:
        try:
            async with self._db.get_session() as session:
                stmt = select(func.count()).select_from(ChatMessage)
                if filter_id:
                    stmt = stmt.where(ChatMessage.session_id == filter_id)
                result = await session.execute(stmt)
                return result.scalar_one()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while counting chat messages.",
                error_code="CHAT_MESSAGE_COUNT_ERROR",
                stack_trace=str(e),
            )

    async def create_many(self, entities: List[ChatMessage]) -> List[UUID]:
        if not entities:
            return []

        try:
            async with self._db.get_session() as session:
                session.add_all(entities)
                await session.flush()
                created_ids = [entity.id for entity in entities]
                self._logger.debug(f"Created {len(created_ids)} chat messages")
                return created_ids

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while creating multiple chat messages.",
                error_code="CHAT_MESSAGE_BULK_CREATION_ERROR",
                stack_trace=str(e),
            )

    async def delete_many(self, message_ids: List[UUID]) -> int:
        if not message_ids:
            return 0

        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    delete(ChatMessage).where(ChatMessage.id.in_(message_ids))
                )
                deleted_count = result.rowcount or 0
                self._logger.debug(f"Deleted {deleted_count} chat messages")
                return deleted_count

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting multiple chat messages.",
                error_code="CHAT_MESSAGE_DELETE_ERROR",
                stack_trace=str(e),
            )
