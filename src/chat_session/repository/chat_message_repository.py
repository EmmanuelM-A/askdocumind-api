"""
Repository interface for chat message CRUD operations.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from fastapi_pagination import Page
from pydantic import BaseModel

from src.chat_session.domain.chat import ChatMessageRole
from src.chat_session.models.chat_message import ChatMessage
from src.database.utils import Pagination


class ChatMessageSearchFilter(BaseModel):
    """Optional criteria for narrowing a user's chat messages."""

    chat_session_id: UUID | None = None
    role: ChatMessageRole | None = None


class ChatMessageRepository(ABC):
    """
    Abstract interface for chat message repository operations.

    Defines the contract for all chat-message-related database operations.
    Concrete implementations must implement all abstract methods.
    """

    @abstractmethod
    async def create(self, data: ChatMessage) -> ChatMessage:
        """
        Create and persist a new chat message entity.
        """
        raise NotImplementedError(
            "The method 'create' must be implemented in its subclass."
        )

    @abstractmethod
    async def list_by_criteria(
        self, user_id: UUID, criteria: ChatMessageSearchFilter | None
    ) -> list[ChatMessage]:
        """
        Retrieve chat messages matching the given criteria.
        """
        raise NotImplementedError(
            "The method 'list_by_criteria' must be implemented in its subclass."
        )

    async def list_by_criteria_paginated(
        self,
        user_id: UUID,
        criteria: ChatMessageSearchFilter | None,
        paginate: Pagination,
    ) -> Page[ChatMessage]:
        """
        Retrieve chat messages matching the given criteria, paginated,
        sorted by creation date in descending order (most recent first).
        """
        raise NotImplementedError(
            "The method 'list_by_criteria_paginated' must be implemented in its subclass."
        )

    @abstractmethod
    async def get_by_id(self, chat_message_id: UUID) -> ChatMessage | None:
        """
        Retrieve a single chat message by its unique identifier.
        """
        raise NotImplementedError(
            "The method 'get_by_id' must be implemented in its subclass."
        )

    @abstractmethod
    async def count(self, chat_session_id: UUID) -> int:
        """
        Count chat messages belonging to a specific chat session.
        """
        raise NotImplementedError(
            "The method 'count' must be implemented in its subclass."
        )

    @abstractmethod
    async def delete_all(self, chat_session_id: UUID) -> int:
        """
        Delete multiple chat messages by their identifiers.
        """
        raise NotImplementedError(
            "The method 'delete_many' must be implemented in its subclass."
        )
