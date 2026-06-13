"""
Chat session management service for handling creation, retrieval, updates, and deletion
of chat sessions with proper authorization and transaction management.
"""

from typing import List, cast
from uuid import UUID

from src.api.services.validation.chat_session import (
    CreateChatSessionSchema,
    DeleteChatSessionSchema,
    GetChatSessionMessagesSchema,
    GetChatSessionSchema,
    InitializeChatSessionSchema,
)
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

    async def create_new_chat(self, data: CreateChatSessionSchema) -> UUID:
        """
        Create a new chat session after verifying max chat limit.
        """

        existing_chats = await self._chat_session_repo.list_by(
            ChatSessionSearchCriteria(user_id=data.owner_id)
        )

        if len(existing_chats) >= settings.app.MAX_CHATS_PER_USER:
            raise unprocessable_entity_error(
                message="User has reached the maximum number of chat allowed per user.",
                error_code="MAX_CHATS_PER_USER_REACHED",
            )

        data = ChatSession(
            title=data.title,
            user_id=data.owner_id,
        )
        created_id = await self._chat_session_repo.create(data=data)

        self._logger.info(
            f"Created new chat session {created_id} for the user {data.owner_id}"
        )

        return created_id

    async def get_chat_metadata(self, data: GetChatSessionSchema) -> dict:
        """
        Retrieve chat session metadata after verifying ownership.
        """

        chat = await check_if_chat_exists(
            chat_id=data.chat_id,
            owner_id=data.owner_id,
            chat_session_repo=self._chat_session_repo,
        )

        self._logger.info(
            f"Retrieved metadata for chat session {data.chat_id} owned by user {data.owner_id}"
        )

        return chat.to_dict()

    async def delete_chat(self, data: DeleteChatSessionSchema) -> UUID:
        """
        Delete a chat session and all associated resources after verifying ownership.
        """
        await check_if_chat_exists(
            chat_id=data.chat_id,
            owner_id=data.owner_id,
            chat_session_repo=self._chat_session_repo,
        )

        deleted_id = await self._chat_session_repo.delete(data.chat_id)

        self._logger.info(f"Deleted the chat session {deleted_id}")

        return deleted_id

    async def init_chat_session(self, data: InitializeChatSessionSchema) -> UUID:
        """
        Initialize a chat session for a user. If the user already has an existing chat,
        return the most recently created chat session. Otherwise, create a new chat session.
        """

        chat = await self._chat_session_repo.get_by_user_id(data.user_id)

        if chat:
            self._logger.info(
                f"Existing chat session {chat.id} found for user {data.user_id}. Returning existing chat."
            )
            return cast(UUID, chat.id)

        self._logger.info(
            f"No existing chat session found for user {data.user_id}. Creating a new one."
        )

        new_chat = ChatSession(
            title=data.title or "New Chat",
            user_id=data.user_id,
        )

        created_id = await self._chat_session_repo.create(data=new_chat)

        self._logger.info(
            f"Created new chat session {created_id} for user {data.user_id}"
        )

        return created_id

    async def get_chat_messages(
        self, data: GetChatSessionMessagesSchema, criteria: ChatMessageSearchCriteria
    ) -> List[dict]:
        """
        Retrieve messages for a specific chat session after verifying ownership.
        """
        await check_if_chat_exists(
            chat_id=data.chat_id,
            owner_id=data.owner_id,
            chat_session_repo=self._chat_session_repo,
        )

        messages = await self._chat_message_repo.list_by(criteria)

        self._logger.info(
            f"Retrieved {len(messages)} messages for chat session {data.chat_id} owned by the user {data.owner_id}"
        )

        return [message.to_dict() for message in messages]
