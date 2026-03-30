"""
Repository interface for chat message CRUD operations.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel

from src.config.constants import ChatMessageRole
from src.database.models import ChatMessage
from src.database.repository.interfaces.db_transaction import DBTransaction


class ChatMessageSearchCriteria(BaseModel):
    """Criteria for filtering chat messages in list/search operations."""

    id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    role: Optional[ChatMessageRole] = None


class UpdatedChatMessageData(BaseModel):
    """Schema for updating chat message fields."""

    content: Optional[str] = None
    role: Optional[ChatMessageRole] = None


class ChatMessageRepositoryInterface(ABC):
    """
    Abstract interface for chat message repository operations.

    Defines the contract for all chat-message-related database operations.
    Concrete implementations must implement all abstract methods.
    """

    @abstractmethod
    async def create(
        self, data: ChatMessage, tx: Optional[DBTransaction] = None
    ) -> UUID:
        """
        Create and persist a new chat message entity.

        :param data: The ChatMessage entity to persist.
        :param tx: Optional transaction object.
        :return: The UUID of the newly created chat message.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_by(
        self,
        criteria: Optional[ChatMessageSearchCriteria] = None,
        tx: Optional[DBTransaction] = None,
    ) -> List[ChatMessage]:
        """
        Retrieve chat messages matching the given criteria.

        Returns all chat messages if no criteria is provided.

        :param criteria: Optional search criteria to filter chat messages.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: List of ChatMessage entities matching the criteria.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(
        self, message_id: UUID, tx: Optional[DBTransaction] = None
    ) -> Optional[ChatMessage]:
        """
        Retrieve a single chat message by its unique identifier.

        :param message_id: The UUID of the chat message to retrieve.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The ChatMessage entity if found, None otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_criteria(
        self,
        criteria: ChatMessageSearchCriteria,
        tx: Optional[DBTransaction] = None,
    ) -> Optional[ChatMessage]:
        """
        Retrieve a single chat message matching the given criteria.

        Returns the first match if multiple messages satisfy the criteria.

        :param criteria: The search criteria to filter by.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The first ChatMessage entity matching criteria, or None.
        """
        raise NotImplementedError

    @abstractmethod
    async def update(
        self,
        entity_id: UUID,
        new_entity_data: UpdatedChatMessageData,
        tx: Optional[DBTransaction] = None,
    ) -> Optional[ChatMessage]:
        """
        Update an existing chat message with new data.

        :param entity_id: The UUID of the chat message to update.
        :param new_entity_data: The update payload containing new field values.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The updated ChatMessage entity if found, None otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(
        self, message_id: UUID, tx: Optional[DBTransaction] = None
    ) -> bool:
        """
        Delete a chat message by its unique identifier.

        :param message_id: The UUID of the chat message to delete.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: True if chat message was deleted, False if not found.
        """
        raise NotImplementedError

    @abstractmethod
    async def exists(
        self, entity_id: UUID, tx: Optional[DBTransaction] = None
    ) -> bool:
        """
        Check if a chat message with the given UUID exists.

        :param entity_id: The UUID to check for existence.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: True if the chat message exists, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def count(
        self,
        filter_id: Optional[UUID] = None,
        tx: Optional[DBTransaction] = None,
    ) -> int:
        """
        Count chat messages, optionally filtered by chat session ID.

        :param filter_id: Optional chat session UUID to filter by.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The count of chat messages matching the filter.
        """
        raise NotImplementedError

    @abstractmethod
    async def create_many(
        self, entities: List[ChatMessage], tx: Optional[DBTransaction] = None
    ) -> List[UUID]:
        """
        Create and persist multiple chat message entities.

        :param entities: List of ChatMessage entities to persist.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: List of UUIDs for the newly created chat messages.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete_many(
        self, message_ids: List[UUID], tx: Optional[DBTransaction] = None
    ) -> int:
        """
        Delete multiple chat messages by their identifiers.

        :param message_ids: List of chat message UUIDs to delete.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The number of chat messages successfully deleted.
        """
        raise NotImplementedError
