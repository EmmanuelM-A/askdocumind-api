"""
Repository interface for chat session CRUD operations.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from fastapi_pagination import Page

from src.chat_session.models.chat_session import ChatSession
from src.database import Pagination


class ChatSessionRepository(ABC):
    """
    Abstract interface for chat session repository operations.

    Defines the contract for all chat-session-related database operations.
    Concrete implementations must implement all abstract methods.
    """

    @abstractmethod
    async def create(self, data: ChatSession) -> ChatSession:
        """
        Create and persist a new chat session entity.
        """
        raise NotImplementedError(
            "The method 'create' must be implemented in its subclass."
        )

    @abstractmethod
    async def list_by_owner(self, user_id: UUID) -> list[ChatSession]:
        """
        Retrieve all chat sessions belonging to the specified user, sorted
        by creation date in descending order (most recent first).
        """
        raise NotImplementedError(
            "The method 'list_by_owner' must be implemented in its subclass."
        )

    @abstractmethod
    async def list_by_owner_paginated(
        self, user_id: UUID, paginate: Pagination
    ) -> Page[ChatSession]:
        """
        Retrieve all chat sessions belonging to the specified user, paginated,
        sorted by creation date in descending order (most recent first).
        """
        raise NotImplementedError(
            "The method 'list_by_owner_paginated' must be implemented in its subclass."
        )

    @abstractmethod
    async def get_by_id(self, chat_session_id: UUID) -> ChatSession | None:
        """
        Retrieve a chat session by its unique identifier.
        """
        raise NotImplementedError(
            "The method 'get_by_id' must be implemented in its subclass."
        )

    @abstractmethod
    async def get_by_user_id(self, user_id: UUID) -> ChatSession | None:
        """
        Retrieve the most recently created chat session for a given user.
        """
        raise NotImplementedError(
            "The method 'get_by_user_id' must be implemented in its subclass."
        )

    @abstractmethod
    async def delete(self, chat_session_id: UUID) -> None:
        """
        Delete a chat session by its unique identifier.
        """
        raise NotImplementedError(
            "The method 'delete' must be implemented in its subclass."
        )

    @abstractmethod
    async def count(self, user_id: UUID) -> int:
        """
        Count chat sessions belonging to a specific user.
        """
        raise NotImplementedError(
            "The method 'count' must be implemented in its subclass."
        )

    @abstractmethod
    async def delete_many(self, chat_sessions_ids: list[UUID]) -> int:
        """
        Delete multiple chat sessions by their identifiers.
        """
        raise NotImplementedError(
            "The method 'delete_many' must be implemented in its subclass."
        )
