"""
Repository interface for chat session CRUD operations.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel

from src.database.models import ChatSession
from src.database.repository.interfaces.db_transaction import DBTransaction


class ChatSessionSearchCriteria(BaseModel):
    """Criteria for filtering chat sessions in list/search operations."""

    id: Optional[UUID] = None
    title: Optional[str] = None
    total_messages: Optional[int] = None


class UpdatedChatSessionData(BaseModel):
    """Schema for updating chat session fields."""

    title: Optional[str] = None


class ChatSessionRepositoryInterface(ABC):
    """
    Abstract interface for chat session repository operations.

    Defines the contract for all chat-session-related database operations.
    Concrete implementations must implement all abstract methods.
    """

    @abstractmethod
    async def create(
        self, data: ChatSession, tx: Optional[DBTransaction] = None
    ) -> UUID:
        """
        Create and persist a new chat session entity.

        :param data: The ChatSession entity to persist.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The UUID of the newly created chat session.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_by(
        self,
        criteria: Optional[ChatSessionSearchCriteria] = None,
        tx: Optional[DBTransaction] = None,
    ) -> List[ChatSession]:
        """
        Retrieve chat sessions matching the given criteria.

        Returns all chat sessions if no criteria is provided.

        :param criteria: Optional search criteria to filter chat sessions.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: List of ChatSession entities matching the criteria.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(
        self, session_id: UUID, tx: Optional[DBTransaction] = None
    ) -> Optional[ChatSession]:
        """
        Retrieve a single chat session by its unique identifier.

        :param session_id: The UUID of the chat session to retrieve.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The ChatSession entity if found, None otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_criteria(
        self,
        criteria: ChatSessionSearchCriteria,
        tx: Optional[DBTransaction] = None,
    ) -> Optional[ChatSession]:
        """
        Retrieve a single chat session matching the given criteria.

        Returns the first match if multiple sessions satisfy the criteria.

        :param criteria: The search criteria to filter by.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The first ChatSession entity matching criteria, or None.
        """
        raise NotImplementedError

    @abstractmethod
    async def update(
        self,
        chat_id: UUID,
        new_entity_data: UpdatedChatSessionData,
        tx: Optional[DBTransaction] = None,
    ) -> Optional[ChatSession]:
        """
        Update an existing chat session with new data.

        :param chat_id: The UUID of the chat session to update.
        :param new_entity_data: The update payload containing new field values.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The updated ChatSession entity if found, None otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, chat_id: UUID, tx: Optional[DBTransaction] = None) -> UUID:
        """
        Delete a chat session by its unique identifier.

        :param chat_id: The UUID of the chat session to delete.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: True if chat session was deleted, False if not found.
        """
        raise NotImplementedError

    @abstractmethod
    async def exists(self, chat_id: UUID, tx: Optional[DBTransaction] = None) -> bool:
        """
        Check if a chat session with the given UUID exists.

        :param chat_id: The UUID to check for existence.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: True if the chat session exists, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def count(
        self,
        filter_id: Optional[UUID] = None,
        tx: Optional[DBTransaction] = None,
    ) -> int:
        """
        Count chat sessions, optionally filtered by chat session ID.

        :param filter_id: Optional chat session UUID to filter by.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The count of chat sessions matching the filter.
        """
        raise NotImplementedError

    @abstractmethod
    async def create_many(
        self, entities: List[ChatSession], tx: Optional[DBTransaction] = None
    ) -> List[UUID]:
        """
        Create and persist multiple chat session entities.

        :param entities: List of ChatSession entities to persist.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: List of UUIDs for the newly created chat sessions.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete_many(
        self, chat_ids: List[UUID], tx: Optional[DBTransaction] = None
    ) -> int:
        """
        Delete multiple chat sessions by their identifiers.

        :param chat_ids: List of chat session UUIDs to delete.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The number of chat sessions successfully deleted.
        """
        raise NotImplementedError
