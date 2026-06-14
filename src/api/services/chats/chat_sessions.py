"""
Chat session management service for handling creation, retrieval, updates, and deletion
of chat sessions with proper authorization and transaction management.
"""

from typing import List, cast
from uuid import UUID

from src.api.services.validation.chat_session import CreateChatSessionData
from src.api.services.validation.helper import check_if_chat_exists
from src.config.configs import settings
from src.database.models import ChatSession
from src.database.repository.interfaces import (
    ChatSessionRepositoryInterface,
    ChatMessageSearchCriteria,
    ChatMessageRepositoryInterface,
    ChatSessionSearchCriteria,
)
from src.errors.custom_exceptions import unprocessable_entity_error
from src.logger.base_logger import BaseLogger


class ChatSessionService:
    def __init__(
        self,
        chat_session_repo: ChatSessionRepositoryInterface,
        chat_message_repo: ChatMessageRepositoryInterface,
    ) -> None:
        self._chat_session_repo = chat_session_repo
        self._chat_message_repo = chat_message_repo
        self._logger = BaseLogger(__name__)

    async def create_new_chat(self, owner_id: UUID, data: CreateChatSessionData) -> UUID:
        """Create a new chat session after verifying the user hasn't hit their limit."""
        existing_chats = await self._chat_session_repo.list_by(
            ChatSessionSearchCriteria(user_id=owner_id)
        )

        if len(existing_chats) >= settings.app.MAX_CHATS_PER_USER:
            raise unprocessable_entity_error(
                message="User has reached the maximum number of chats allowed per user.",
                error_code="MAX_CHATS_PER_USER_REACHED",
            )

        new_session = ChatSession(title=data.title, user_id=owner_id)
        created_id = await self._chat_session_repo.create(data=new_session)

        self._logger.info(f"Created new chat session {created_id} for user {owner_id}")
        return created_id

    async def init_chat_session(self, user_id: UUID, data: CreateChatSessionData) -> UUID:
        """
        Return the user's most recent chat session, or create a new one if none exists.
        """
        chat = await self._chat_session_repo.get_by_user_id(user_id)

        if chat:
            self._logger.info(
                f"Existing chat session {chat.id} found for user {user_id}."
            )
            return cast(UUID, chat.id)

        new_chat = ChatSession(title=data.title, user_id=user_id)
        created_id = await self._chat_session_repo.create(data=new_chat)

        self._logger.info(f"Created new chat session {created_id} for user {user_id}")
        return created_id

    async def get_chat_metadata(self, chat_id: UUID, owner_id: UUID) -> dict:
        """Retrieve chat session metadata after verifying ownership."""
        chat = await check_if_chat_exists(
            chat_id=chat_id,
            owner_id=owner_id,
            chat_session_repo=self._chat_session_repo,
        )

        self._logger.info(
            f"Retrieved metadata for chat session {chat_id} owned by user {owner_id}"
        )
        return chat.to_dict()

    async def delete_chat(self, chat_id: UUID, owner_id: UUID) -> UUID:
        """Delete a chat session after verifying ownership."""
        await check_if_chat_exists(
            chat_id=chat_id,
            owner_id=owner_id,
            chat_session_repo=self._chat_session_repo,
        )

        deleted_id = await self._chat_session_repo.delete(chat_id)

        self._logger.info(f"Deleted chat session {deleted_id}")
        return deleted_id

    async def get_chat_messages(self, chat_id: UUID, owner_id: UUID) -> List[dict]:
        """Retrieve messages for a chat session after verifying ownership."""
        await check_if_chat_exists(
            chat_id=chat_id,
            owner_id=owner_id,
            chat_session_repo=self._chat_session_repo,
        )

        criteria = ChatMessageSearchCriteria(session_id=chat_id)
        messages = await self._chat_message_repo.list_by(criteria)

        self._logger.info(
            f"Retrieved {len(messages)} messages for chat session {chat_id}"
        )
        return [message.to_dict() for message in messages]
