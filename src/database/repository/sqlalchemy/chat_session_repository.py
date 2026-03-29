"""
Responsible for managing chat session storage in the remote database.
"""

from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.database.connection import DatabaseConnection
from src.database.models import ChatSession
from src.database.repository.interfaces.chat_session_repository import (
    ChatSessionRepositoryInterface,
    ChatSessionSearchCriteria,
    UpdatedChatSessionData,
)
from src.errors.custom_exceptions import database_error
from src.logger.base_logger import BaseLogger


class ChatSessionRepository(ChatSessionRepositoryInterface):
    """
    Concrete implementation of the chat session repository interface.
    """

    def __init__(self, connection: DatabaseConnection) -> None:
        self._db = connection
        self._logger = BaseLogger(__name__)

    async def create(self, entity: ChatSession) -> UUID:
        try:
            async with self._db.get_session() as session:
                session.add(entity)
                await session.flush()
                self._logger.debug(f"New chat session created: {entity.id}")
                return entity.id

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while creating a new chat session.",
                error_code="CHAT_SESSION_CREATION_ERROR",
                stack_trace=str(e),
            )

    async def list_by(
        self, criteria: Optional[ChatSessionSearchCriteria] = None
    ) -> List[ChatSession]:
        try:
            async with self._db.get_session() as session:
                stmt = select(ChatSession)

                if criteria is None:
                    result = await session.execute(stmt)
                    self._logger.debug(
                        "No criteria provided, returning all chat sessions"
                    )
                    return result.scalars().all()

                filters = []

                for field, value in criteria.model_dump(exclude_none=True).items():
                    filters.append(getattr(ChatSession, field) == value)

                stmt = stmt.where(*filters)
                result = await session.execute(stmt)
                self._logger.debug("Found chat sessions matching criteria")
                return result.scalars().all()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while listing chat sessions by criteria.",
                error_code="CHAT_SESSION_LISTING_ERROR",
                stack_trace=str(e),
            )

    async def get_by_id(self, entity_id: UUID) -> Optional[ChatSession]:
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
            raise database_error(
                message="An error occurred while getting chat session by id.",
                error_code="CHAT_SESSION_GET_ERROR",
                stack_trace=str(e),
            )

    async def get_by_criteria(
        self, criteria: ChatSessionSearchCriteria
    ) -> Optional[ChatSession]:
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
            raise database_error(
                message="An error occurred while getting chat session by criteria.",
                error_code="CHAT_SESSION_GET_ERROR",
                stack_trace=str(e),
            )

    async def update(
        self, entity_id: UUID, new_entity_data: UpdatedChatSessionData
    ) -> Optional[ChatSession]:
        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    select(ChatSession).where(ChatSession.id == entity_id)
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    return None

                if (
                    hasattr(new_entity_data, "title")
                    and new_entity_data.title is not None
                ):
                    existing.title = new_entity_data.title

                await session.flush()
                return existing

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while updating chat session.",
                error_code="CHAT_SESSION_UPDATE_ERROR",
                stack_trace=str(e),
            )

    async def delete(self, entity_id: UUID) -> bool:
        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    delete(ChatSession).where(ChatSession.id == entity_id)
                )
                return result.rowcount > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting chat session.",
                error_code="CHAT_SESSION_DELETE_ERROR",
                stack_trace=str(e),
            )

    async def exists(self, entity_id: UUID) -> bool:
        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    select(func.count())
                    .select_from(ChatSession)
                    .where(ChatSession.id == entity_id)
                )
                return result.scalar_one() > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while determining if chat session exists.",
                error_code="CHAT_SESSION_EXISTS_ERROR",
                stack_trace=str(e),
            )

    async def count(self, filter_id: Optional[UUID] = None) -> int:
        try:
            async with self._db.get_session() as session:
                stmt = select(func.count()).select_from(ChatSession)
                if filter_id:
                    stmt = stmt.where(ChatSession.id == filter_id)
                result = await session.execute(stmt)
                return result.scalar_one()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while counting chat sessions.",
                error_code="CHAT_SESSION_COUNT_ERROR",
                stack_trace=str(e),
            )

    async def create_many(self, entities: List[ChatSession]) -> List[UUID]:
        if not entities:
            return []

        try:
            async with self._db.get_session() as session:
                session.add_all(entities)
                await session.flush()
                created_ids = [entity.id for entity in entities]
                self._logger.debug(f"Created {len(created_ids)} chat sessions")
                return created_ids

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while creating multiple chat sessions.",
                error_code="CHAT_SESSION_BULK_CREATION_ERROR",
                stack_trace=str(e),
            )

    async def delete_many(self, session_ids: List[UUID]) -> int:
        if not session_ids:
            return 0

        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    delete(ChatSession).where(ChatSession.id.in_(session_ids))
                )
                deleted_count = result.rowcount or 0
                self._logger.debug(f"Deleted {deleted_count} chat sessions")
                return deleted_count

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting multiple chat sessions.",
                error_code="CHAT_SESSION_DELETE_ERROR",
                stack_trace=str(e),
            )
