from uuid import UUID

from fastapi_pagination import Page
from sqlalchemy import Select, delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.chat_session.models.chat_message import ChatMessage
from src.chat_session.models.chat_session import ChatSession
from src.chat_session.repository.chat_message_repository import (
    ChatMessageRepository,
    ChatMessageSearchFilter,
)
from src.database import Pagination
from src.database.utils import BaseRepository
from src.exceptions import database_error


def _owned_messages(user_id: UUID, criteria: ChatMessageSearchFilter | None) -> Select:
    """Select messages owned by user_id, narrowed by the optional criteria."""
    statement = (
        select(ChatMessage)
        .join(ChatSession, ChatMessage.chat_session_id == ChatSession.id)
        .where(ChatSession.user_id == user_id)
    )

    if criteria is None:
        return statement

    if criteria.chat_session_id is not None:
        statement = statement.where(
            ChatMessage.chat_session_id == criteria.chat_session_id
        )
    if criteria.role is not None:
        statement = statement.where(ChatMessage.role == criteria.role)

    return statement


class ChatMessageRepositoryImpl(ChatMessageRepository, BaseRepository):
    """
    Concrete implementation of the ChatMessageRepository interface.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(self, data: ChatMessage) -> ChatMessage:
        try:
            self._session.add(data)
            await self._session.flush()
            return data
        except Exception as e:
            raise database_error(
                message="An error occurred while creating a chat message.",
                error_code="CHAT_MESSAGE_CREATION_ERROR",
                cause=e,
            ) from e

    async def list_by_criteria(
        self, user_id: UUID, criteria: ChatMessageSearchFilter | None
    ) -> list[ChatMessage]:
        statement = _owned_messages(user_id, criteria).order_by(
            ChatMessage.created_at, ChatMessage.id
        )
        try:
            result = await self._session.execute(statement)
            return list(result.scalars().all())
        except Exception as e:
            raise database_error(
                message="An error occurred while listing chat messages.",
                error_code="CHAT_MESSAGE_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def list_by_criteria_paginated(
        self,
        user_id: UUID,
        criteria: ChatMessageSearchFilter | None,
        paginate: Pagination,
    ) -> Page[ChatMessage]:
        statement = _owned_messages(user_id, criteria).order_by(
            ChatMessage.created_at.desc(), ChatMessage.id.desc()
        )
        try:
            return await self._paginate(statement, paginate)
        except Exception as e:
            raise database_error(
                message="An error occurred while listing chat messages.",
                error_code="CHAT_MESSAGE_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def get_by_id(self, chat_message_id: UUID) -> ChatMessage | None:
        statement = select(ChatMessage).where(ChatMessage.id == chat_message_id)
        try:
            result = await self._session.execute(statement)
            return result.scalar_one_or_none()
        except Exception as e:
            raise database_error(
                message="An error occurred while retrieving the chat message.",
                error_code="CHAT_MESSAGE_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def count(self, chat_session_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.chat_session_id == chat_session_id)
        )
        try:
            return (await self._session.execute(statement)).scalar_one()
        except Exception as e:
            raise database_error(
                message="An error occurred while counting chat messages.",
                error_code="CHAT_MESSAGE_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def delete_many(self, chat_message_ids: list[UUID]) -> int:
        if not chat_message_ids:
            return 0

        statement = delete(ChatMessage).where(ChatMessage.id.in_(chat_message_ids))
        try:
            result = await self._session.execute(statement)
            return result.rowcount
        except Exception as e:
            raise database_error(
                message="An error occurred while deleting chat messages.",
                error_code="CHAT_MESSAGE_DELETION_ERROR",
                cause=e,
            ) from e
