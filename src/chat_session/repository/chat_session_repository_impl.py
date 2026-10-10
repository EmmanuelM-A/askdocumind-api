from uuid import UUID

from fastapi_pagination import Page
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.chat_session.models.chat_session import ChatSession
from src.chat_session.repository.chat_session_repository import ChatSessionRepository
from src.database.utils import Pagination
from src.database.utils import BaseRepository
from src.exceptions import database_error


class ChatSessionRepositoryImpl(ChatSessionRepository, BaseRepository):
    """
    Concrete implementation of the ChatSessionRepository interface.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def create(self, data: ChatSession) -> ChatSession:
        try:
            self._session.add(data)
            await self._session.flush()
            return data
        except Exception as e:
            raise database_error(
                message="An error occurred while creating a chat session.",
                error_code="CHAT_SESSION_CREATION_ERROR",
                cause=e,
            ) from e

    async def list_by_owner(self, user_id: UUID) -> list[ChatSession]:
        statement = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.created_at.desc(), ChatSession.id.desc())
        )
        try:
            result = await self._session.execute(statement)
            return list(result.scalars().all())
        except Exception as e:
            raise database_error(
                message="An error occurred while listing chat sessions.",
                error_code="CHAT_SESSION_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def list_by_owner_paginated(
        self, user_id: UUID, paginate: Pagination
    ) -> Page[ChatSession]:
        statement = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.created_at.desc(), ChatSession.id.desc())
        )
        try:
            return await self._paginate(statement, paginate)
        except Exception as e:
            raise database_error(
                message="An error occurred while listing chat sessions.",
                error_code="CHAT_SESSION_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def get_by_id(self, chat_session_id: UUID) -> ChatSession | None:
        statement = select(ChatSession).where(ChatSession.id == chat_session_id)
        try:
            result = await self._session.execute(statement)
            return result.scalars().first()
        except Exception as e:
            raise database_error(
                message="An error occurred while retrieving the chat session.",
                error_code="CHAT_SESSION_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def get_by_user_id(self, user_id: UUID) -> ChatSession | None:
        statement = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.created_at.desc(), ChatSession.id.desc())
            .limit(1)
        )
        try:
            result = await self._session.execute(statement)
            return result.scalars().first()
        except Exception as e:
            raise database_error(
                message="An error occurred while retrieving the chat session.",
                error_code="CHAT_SESSION_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def delete(self, chat_session_id: UUID) -> None:
        statement = delete(ChatSession).where(ChatSession.id == chat_session_id)
        try:
            result = await self._session.execute(statement)
        except Exception as e:
            raise database_error(
                message="An error occurred while deleting the chat session.",
                error_code="CHAT_SESSION_DELETION_ERROR",
                cause=e,
            ) from e

        if result.rowcount == 0:
            raise database_error(
                message="The chat session to delete was not found.",
                error_code="CHAT_SESSION_NOT_FOUND",
            )

    async def delete_many(self, chat_sessions_ids: list[UUID]) -> int:
        if not chat_sessions_ids:
            return 0

        statement = delete(ChatSession).where(ChatSession.id.in_(chat_sessions_ids))
        try:
            result = await self._session.execute(statement)
            return result.rowcount
        except Exception as e:
            raise database_error(
                message="An error occurred while deleting chat sessions.",
                error_code="CHAT_SESSION_DELETION_ERROR",
                cause=e,
            ) from e

    async def count(self, user_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(ChatSession)
            .where(ChatSession.user_id == user_id)
        )
        try:
            return (await self._session.execute(statement)).scalar_one()
        except Exception as e:
            raise database_error(
                message="An error occurred while counting chat sessions.",
                error_code="CHAT_SESSION_COUNT_ERROR",
                cause=e,
            ) from e
