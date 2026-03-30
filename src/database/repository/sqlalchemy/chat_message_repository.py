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
from src.database.repository.interfaces.db_transaction import DBTransaction
from src.errors.custom_exceptions import database_error
from src.logger.base_logger import BaseLogger


class ChatMessageRepository(ChatMessageRepositoryInterface):
    """
    Concrete implementation of the chat message repository interface.
    """

    def __init__(self, connection: DatabaseConnection) -> None:
        self._db = connection
        self._logger = BaseLogger(__name__)

    @staticmethod
    def _build_filters(criteria: ChatMessageSearchCriteria) -> list:
        filters = []
        for field, value in criteria.model_dump(exclude_none=True).items():
            filters.append(getattr(ChatMessage, field) == value)
        return filters

    async def create(
        self, data: ChatMessage, tx: Optional[DBTransaction] = None
    ) -> UUID:
        try:
            if tx is not None:
                await tx.add(data)
                await tx.flush()
                self._logger.debug(f"New chat message entry created: {data.id}")
                return data.id

            async with self._db.get_session() as session:
                session.add(data)
                await session.flush()
                self._logger.debug(f"New chat message entry created: {data.id}")
                return data.id

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while creating a new chat message.",
                error_code="CHAT_MESSAGE_CREATION_ERROR",
                stack_trace=str(e),
            )

    async def list_by(
        self,
        criteria: Optional[ChatMessageSearchCriteria] = None,
        tx: Optional[DBTransaction] = None,
    ) -> List[ChatMessage]:
        try:
            stmt = select(ChatMessage)

            if criteria is not None:
                stmt = stmt.where(*self._build_filters(criteria))

            if tx is not None:
                result = await tx.execute(stmt)
                if criteria is None:
                    self._logger.debug(
                        "No criteria provided, returning all chat messages"
                    )
                else:
                    self._logger.debug("Found chat messages matching criteria")
                return result.scalars().all()

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                if criteria is None:
                    self._logger.debug(
                        "No criteria provided, returning all chat messages"
                    )
                    return result.scalars().all()
                self._logger.debug("Found chat messages matching criteria")
                return result.scalars().all()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while listing chat messages by criteria.",
                error_code="CHAT_MESSAGE_LISTING_ERROR",
                stack_trace=str(e),
            )

    async def get_by_id(
        self, message_id: UUID, tx: Optional[DBTransaction] = None
    ) -> Optional[ChatMessage]:
        try:
            stmt = select(ChatMessage).where(ChatMessage.id == message_id)

            if tx is not None:
                result = await tx.execute(stmt)
                chat_message = result.scalar_one_or_none()
                if chat_message:
                    self._logger.debug(
                        "Found chat message entry matching the provided ID"
                    )
                return chat_message

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
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
        self,
        criteria: ChatMessageSearchCriteria,
        tx: Optional[DBTransaction] = None,
    ) -> Optional[ChatMessage]:
        try:
            filters = self._build_filters(criteria)

            if not filters:
                self._logger.debug("No chat messages matching criteria")
                return None

            stmt = select(ChatMessage).where(*filters)

            if tx is not None:
                result = await tx.execute(stmt)
                self._logger.debug("Found chat messages matching criteria")
                return result.scalars().first()

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                self._logger.debug("Found chat messages matching criteria")
                return result.scalars().first()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while getting chat message by criteria.",
                error_code="CHAT_MESSAGE_GET_ERROR",
                stack_trace=str(e),
            )

    async def update(
        self,
        entity_id: UUID,
        new_entity_data: UpdatedChatMessageData,
        tx: Optional[DBTransaction] = None,
    ) -> Optional[ChatMessage]:
        try:
            stmt = select(ChatMessage).where(ChatMessage.id == entity_id)

            if tx is not None:
                result = await tx.execute(stmt)
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

                await tx.flush()
                return existing

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
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

    async def delete(
        self, message_id: UUID, tx: Optional[DBTransaction] = None
    ) -> bool:
        try:
            stmt = delete(ChatMessage).where(ChatMessage.id == message_id)

            if tx is not None:
                result = await tx.execute(stmt)
                return (result.rowcount or 0) > 0

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return (result.rowcount or 0) > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting chat message.",
                error_code="CHAT_MESSAGE_DELETE_ERROR",
                stack_trace=str(e),
            )

    async def exists(
        self, entity_id: UUID, tx: Optional[DBTransaction] = None
    ) -> bool:
        try:
            stmt = (
                select(func.count())
                .select_from(ChatMessage)
                .where(ChatMessage.id == entity_id)
            )

            if tx is not None:
                result = await tx.execute(stmt)
                return result.scalar_one() > 0

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return result.scalar_one() > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while determining if chat message exists.",
                error_code="CHAT_MESSAGE_EXISTS_ERROR",
                stack_trace=str(e),
            )

    async def count(
        self,
        filter_id: Optional[UUID] = None,
        tx: Optional[DBTransaction] = None,
    ) -> int:
        try:
            stmt = select(func.count()).select_from(ChatMessage)
            if filter_id:
                stmt = stmt.where(ChatMessage.session_id == filter_id)

            if tx is not None:
                result = await tx.execute(stmt)
                return result.scalar_one()

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return result.scalar_one()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while counting chat messages.",
                error_code="CHAT_MESSAGE_COUNT_ERROR",
                stack_trace=str(e),
            )

    async def create_many(
        self, entities: List[ChatMessage], tx: Optional[DBTransaction] = None
    ) -> List[UUID]:
        if not entities:
            return []

        try:
            if tx is not None:
                await tx.add_all(entities)
                await tx.flush()
                created_ids = [entity.id for entity in entities]
                self._logger.debug(f"Created {len(created_ids)} chat messages")
                return created_ids

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

    async def delete_many(
        self, message_ids: List[UUID], tx: Optional[DBTransaction] = None
    ) -> int:
        if not message_ids:
            return 0

        try:
            stmt = delete(ChatMessage).where(ChatMessage.id.in_(message_ids))

            if tx is not None:
                result = await tx.execute(stmt)
                deleted_count = result.rowcount or 0
                self._logger.debug(f"Deleted {deleted_count} chat messages")
                return deleted_count

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                deleted_count = result.rowcount or 0
                self._logger.debug(f"Deleted {deleted_count} chat messages")
                return deleted_count

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting multiple chat messages.",
                error_code="CHAT_MESSAGE_DELETE_ERROR",
                stack_trace=str(e),
            )
