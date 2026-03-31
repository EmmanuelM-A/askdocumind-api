"""
Service module
"""

from typing import List
from uuid import UUID

from src.api.services.validation.schemas import (
    CreateChatSchema,
)
from src.components.chatbot.core import RAGChatbot
from src.database.models import ChatSession, ChatMessage
from src.database.repository.interfaces import (
    ChatSessionRepositoryInterface,
    DBTransactionFactory,
    UpdatedChatSessionData,
    ChatMessageSearchCriteria,
    ChatMessageRepositoryInterface,
)
from src.database.storage import StorageService
from src.errors.custom_exceptions import not_found_error
from src.logger.base_logger import BaseLogger


class ChatSessionService:
    def __init__(
        self,
        chatbot: RAGChatbot,
        storage: StorageService,
        chat_session_repo: ChatSessionRepositoryInterface,
        chat_message_repo: ChatMessageRepositoryInterface,
        tx_factory: DBTransactionFactory,
    ) -> None:
        self.chatbot = chatbot
        self.storage = storage
        self.chat_session_repo = chat_session_repo
        self.chat_message_repo = chat_message_repo
        self.tx_factory = tx_factory
        self._logger = BaseLogger(__name__)

    async def create_new_chat(self, chat_data: CreateChatSchema) -> UUID:
        async with self.tx_factory.create() as tx:
            data = ChatSession(title=chat_data.title)
            created_id = await self.chat_session_repo.create(
                data=data,
                tx=tx,
            )

            self.chatbot.create_chat(index_chat_id=str(created_id))

            return created_id

    async def get_chat_metadata(self, chat_id: UUID) -> ChatSession:
        chat = await self.chat_session_repo.get_by_id(chat_id)

        if chat is None:
            raise not_found_error(
                "The chat with the provided id was not found." "CHAT_NOT_FOUND"
            )

        return chat

    async def update_chat_metadata(
        self, chat_id: UUID, data: UpdatedChatSessionData
    ) -> ChatSession:
        updated_chat = await self.chat_session_repo.update(
            chat_id=chat_id,
            new_entity_data=data,
        )

        if updated_chat is None:
            raise not_found_error(
                "The chat with the provided id was not found." "CHAT_NOT_FOUND"
            )

        return updated_chat

    async def delete_chat(self, chat_id: UUID) -> UUID:
        exists = await self.chat_session_repo.exists(chat_id)

        if not exists:
            raise not_found_error(
                message="The chat with the provided id was not found.",
                error_code="CHAT_NOT_FOUND",
            )

        async with self.tx_factory.create() as tx:
            # Delete metadata
            deleted_id = await self.chat_session_repo.delete(chat_id, tx)

            # Delete all uploaded files
            self.storage.delete_all(str(chat_id))

            # Delete all vector indexes associated
            self.chatbot.delete_chat(str(chat_id))

            return deleted_id

    async def get_chat_messages(
        self, criteria: ChatMessageSearchCriteria
    ) -> List[ChatMessage]:
        return await self.chat_message_repo.list_by(criteria)
