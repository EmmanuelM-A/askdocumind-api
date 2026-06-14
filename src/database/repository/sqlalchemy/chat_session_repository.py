"""
Responsible for managing chat session storage in the remote database.
"""

from typing import Optional, List, cast
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
from src.database.repository.interfaces.db_transaction import DBTransaction
from src.errors.custom_exceptions import database_error
from src.logger.base_logger import BaseLogger


class ChatSessionRepository(ChatSessionRepositoryInterface):
    """
    Concrete implementation of the chat session repository interface.
    """

    def __init__(self, connection: DatabaseConnection) -> None:
        self._db = connection
        self._logger = BaseLogger(__name__)

    @staticmethod
    def _build_filters(criteria: ChatSessionSearchCriteria) -> list:
        filters = []
        for field, value in criteria.model_dump(exclude_none=True).items():
            filters.append(getattr(ChatSession, field) == value)
        return filters

    async def create(
        self, data: ChatSession, tx: Optional[DBTransaction] = None
    ) -> UUID:
        try:
            if tx is not None:
                await tx.add(data)
                await tx.flush()
                self._logger.debug(f"New chat session created: {data.id}")
                return cast(UUID, data.id)

            async with self._db.get_session() as session:
                session.add(data)
                await session.flush()
                self._logger.debug(f"New chat session created: {data.id}")
                return cast(UUID, data.id)

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while creating a new chat session.",
                error_code="CHAT_SESSION_CREATION_ERROR",
                stack_trace=str(e),
            )

    async def list_by(
        self,
        criteria: Optional[ChatSessionSearchCriteria] = None,
        tx: Optional[DBTransaction] = None,
    ) -> List[ChatSession]:
        try:
            stmt = select(ChatSession)

            if criteria is not None:
                stmt = stmt.where(*self._build_filters(criteria))

            if tx is not None:
                result = await tx.execute(stmt)
                if criteria is None:
                    self._logger.debug(
                        "No criteria provided, returning all chat sessions"
                    )
                else:
                    self._logger.debug("Found chat sessions matching criteria")
                return result.scalars().all()

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                if criteria is None:
                    self._logger.debug(
                        "No criteria provided, returning all chat sessions"
                    )
                    return result.scalars().all()
                self._logger.debug("Found chat sessions matching criteria")
                return result.scalars().all()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while listing chat sessions by criteria.",
                error_code="CHAT_SESSION_LISTING_ERROR",
                stack_trace=str(e),
            )

    async def get_by_id(
        self, session_id: UUID, tx: Optional[DBTransaction] = None
    ) -> Optional[ChatSession]:
        try:
            stmt = select(ChatSession).where(ChatSession.id == session_id)

            if tx is not None:
                result = await tx.execute(stmt)
                chat_session = result.scalar_one_or_none()
                if chat_session:
                    self._logger.debug(f"Found chat session: {session_id}")
                return chat_session

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                chat_session = result.scalar_one_or_none()
                if chat_session:
                    self._logger.debug(f"Found chat session: {session_id}")
                return chat_session

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while getting chat session by id.",
                error_code="CHAT_SESSION_GET_ERROR",
                stack_trace=str(e),
            )

    async def get_by_user_id(
        self, user_id: UUID, tx: Optional[DBTransaction] = None
    ) -> Optional[ChatSession]:
        try:
            stmt = (
                select(ChatSession)
                .where(ChatSession.user_id == user_id)
                .order_by(ChatSession.created_at.desc())
                .limit(1)
            )

            if tx is not None:
                result = await tx.execute(stmt)
                chat_session = result.scalar_one_or_none()
                if chat_session:
                    self._logger.debug(f"Found most recent chat session for user: {user_id}")
                return chat_session

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                chat_session = result.scalar_one_or_none()
                if chat_session:
                    self._logger.debug(f"Found most recent chat session for user: {user_id}")
                return chat_session

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while getting chat session by user ID.",
                error_code="CHAT_SESSION_GET_BY_USER_ERROR",
                stack_trace=str(e),
            )

    async def get_by_criteria(
        self,
        criteria: ChatSessionSearchCriteria,
        tx: Optional[DBTransaction] = None,
    ) -> Optional[ChatSession]:
        try:
            filters = self._build_filters(criteria)

            if not filters:
                self._logger.debug("No criteria provided for get_by_criteria")
                return None

            stmt = select(ChatSession).where(*filters)

            if tx is not None:
                result = await tx.execute(stmt)
                self._logger.debug("Found chat session matching criteria")
                return result.scalars().first()

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                self._logger.debug("Found chat session matching criteria")
                return result.scalars().first()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while getting chat session by criteria.",
                error_code="CHAT_SESSION_GET_ERROR",
                stack_trace=str(e),
            )

    async def update(
        self,
        chat_id: UUID,
        new_entity_data: UpdatedChatSessionData,
        tx: Optional[DBTransaction] = None,
    ) -> Optional[ChatSession]:
        try:
            stmt = select(ChatSession).where(ChatSession.id == chat_id)

            if tx is not None:
                result = await tx.execute(stmt)
                existing = result.scalar_one_or_none()

                if not existing:
                    return None

                if (
                    hasattr(new_entity_data, "title")
                    and new_entity_data.title is not None
                ):
                    existing.title = new_entity_data.title

                await tx.flush()
                return existing

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
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

    async def delete(self, chat_id: UUID, tx: Optional[DBTransaction] = None) -> UUID:
        try:
            stmt = delete(ChatSession).where(ChatSession.id == chat_id)
            if tx is not None:
                await tx.execute(stmt)
            else:
                async with self._db.get_session() as session:
                    await session.execute(stmt)

            return chat_id

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting chat session.",
                error_code="CHAT_SESSION_DELETE_ERROR",
                stack_trace=str(e),
            )

    async def exists(self, chat_id: UUID, tx: Optional[DBTransaction] = None) -> bool:
        try:
            stmt = (
                select(func.count())
                .select_from(ChatSession)
                .where(ChatSession.id == chat_id)
            )

            if tx is not None:
                result = await tx.execute(stmt)
                return result.scalar_one() > 0

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return result.scalar_one() > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while determining if chat session exists.",
                error_code="CHAT_SESSION_EXISTS_ERROR",
                stack_trace=str(e),
            )

    async def count(
        self,
        filter_id: Optional[UUID] = None,
        tx: Optional[DBTransaction] = None,
    ) -> int:
        try:
            stmt = select(func.count()).select_from(ChatSession)
            if filter_id:
                stmt = stmt.where(ChatSession.id == filter_id)

            if tx is not None:
                result = await tx.execute(stmt)
                return result.scalar_one()

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return result.scalar_one()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while counting chat sessions.",
                error_code="CHAT_SESSION_COUNT_ERROR",
                stack_trace=str(e),
            )

    async def create_many(
        self, entities: List[ChatSession], tx: Optional[DBTransaction] = None
    ) -> List[UUID]:
        if not entities:
            return []

        try:
            if tx is not None:
                await tx.add_all(entities)
                await tx.flush()
                created_ids = [entity.id for entity in entities]
                self._logger.debug(f"Created {len(created_ids)} chat sessions")
                return cast(List[UUID], created_ids)

            async with self._db.get_session() as session:
                session.add_all(entities)
                await session.flush()
                created_ids = [entity.id for entity in entities]
                self._logger.debug(f"Created {len(created_ids)} chat sessions")
                return cast(List[UUID], created_ids)

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while creating multiple chat sessions.",
                error_code="CHAT_SESSION_BULK_CREATION_ERROR",
                stack_trace=str(e),
            )

    async def delete_many(
        self, chat_ids: List[UUID], tx: Optional[DBTransaction] = None
    ) -> int:
        if not chat_ids:
            return 0

        try:
            stmt = delete(ChatSession).where(ChatSession.id.in_(chat_ids))

            if tx is not None:
                result = await tx.execute(stmt)
                deleted_count = result.rowcount or 0
                self._logger.debug(f"Deleted {deleted_count} chat sessions")
                return deleted_count

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                deleted_count = result.rowcount or 0
                self._logger.debug(f"Deleted {deleted_count} chat sessions")
                return deleted_count

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting multiple chat sessions.",
                error_code="CHAT_SESSION_DELETE_ERROR",
                stack_trace=str(e),
            )
