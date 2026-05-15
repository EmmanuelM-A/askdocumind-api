"""
Chat session management service for handling creation, retrieval, updates, and deletion
of chat sessions with proper authorization and transaction management.
"""

from typing import List
from uuid import UUID

from src.api.services.auth.anonymous_identity import require_current_anonymous_user_id
from src.api.services.validation.schemas import (
    CreateChatSchema,
)
from src.config.configs import settings
from src.database.models import ChatSession, ChatMessage
from src.database.repository.interfaces import (
    ChatSessionRepositoryInterface,
    DBTransactionFactory,
    UpdatedChatSessionData,
    ChatMessageSearchCriteria,
    ChatMessageRepositoryInterface,
    ChatSessionSearchCriteria,
)
from src.database.storage import StorageService
from src.errors.custom_exceptions import not_found_error, unprocessable_entity_error
from src.logger.base_logger import BaseLogger


class ChatSessionService:
    def __init__(
        self,
        storage: StorageService,
        chat_session_repo: ChatSessionRepositoryInterface,
        chat_message_repo: ChatMessageRepositoryInterface,
        tx_factory: DBTransactionFactory,
    ) -> None:
        self.storage = storage
        self.chat_session_repo = chat_session_repo
        self.chat_message_repo = chat_message_repo
        self.tx_factory = tx_factory
        self._logger = BaseLogger(__name__)

    async def _get_owned_chat(self, chat_id: UUID) -> ChatSession:
        """Fetch a chat session owned by the current anonymous user."""

        current_user_id = require_current_anonymous_user_id()
        chat = await self.chat_session_repo.get_by_criteria(
            ChatSessionSearchCriteria(id=chat_id, user_id=current_user_id)
        )

        if chat is None:
            raise not_found_error(
                message="The chat with the provided id was not found.",
                error_code="CHAT_NOT_FOUND",
            )

        return chat

    async def create_new_chat(self, chat_data: CreateChatSchema) -> UUID:
        """Create a new chat session after verifying max chat limit."""
        current_user_id = require_current_anonymous_user_id()

        async with self.tx_factory.create() as tx:
            existing_chats = await self.chat_session_repo.list_by(
                ChatSessionSearchCriteria(user_id=current_user_id)
            )

            if len(existing_chats) >= settings.server.MAX_CHATS_PER_USER:
                raise unprocessable_entity_error(
                    message="User has reached the maximum number of chat allowed per user.",
                    error_code="MAX_CHATS_PER_USER_REACHED",
                )

            data = ChatSession(
                title=chat_data.title,
                user_id=current_user_id,
            )
            created_id = await self.chat_session_repo.create(
                data=data,
                tx=tx,
            )

            return created_id

    async def get_chat_metadata(self, chat_id: UUID) -> ChatSession:
        return await self._get_owned_chat(chat_id)

    async def update_chat_metadata(
        self, chat_id: UUID, data: UpdatedChatSessionData
    ) -> ChatSession:
        """Update chat metadata after verifying ownership.

        The None check for updated_chat handles the rare race condition where the chat
        is deleted between the ownership check and the update operation.
        """
        await self._get_owned_chat(chat_id)

        updated_chat = await self.chat_session_repo.update(
            chat_id=chat_id,
            new_entity_data=data,
        )

        if updated_chat is None:
            self._logger.warning(
                f"Chat {chat_id} was deleted before update could be applied (race condition)"
            )
            raise not_found_error(
                message="The chat with the provided id was not found.",
                error_code="CHAT_NOT_FOUND",
            )

        return updated_chat

    async def delete_chat(self, chat_id: UUID) -> UUID:
        """Delete a chat session and all associated files.

        Database deletion happens first within a transaction. Storage deletion
        happens afterward to ensure consistency, with logging for any failures.
        """
        await self._get_owned_chat(chat_id)

        async with self.tx_factory.create() as tx:
            # Delete metadata from database first
            deleted_id = await self.chat_session_repo.delete(chat_id, tx)

        # Delete all uploaded files after successful database delete
        try:
            self.storage.delete_all(str(chat_id))
        except Exception as e:
            self._logger.error(
                f"Failed to delete storage for chat {chat_id}: {e}. "
                f"Database entry deleted but files remain.",
                exc_info=True,
            )
            # Re-raise to notify caller, but database cleanup already succeeded
            raise

        return deleted_id

    async def init_or_get_chat_session(self, user_id: UUID, title: str = None) -> UUID:
        """Initialize or retrieve a chat session for the given user.

        Verifies that the provided user_id matches the current authenticated user,
        then either retrieves the most recent chat or creates a new one.

        Args:
            user_id: The user ID to get/create chat for (must match current user)
            title: Optional title for newly created chat sessions

        Returns:
            UUID of an existing or newly created chat session
        """
        # Verify the provided user_id matches the current authenticated user
        current_user_id = require_current_anonymous_user_id()
        if user_id != current_user_id:
            raise not_found_error(
                message="User ID does not match current user.",
                error_code="UNAUTHORIZED_USER_ID",
            )

        # Try to retrieve existing chat session for the user
        existing_chats = await self.chat_session_repo.list_by(
            ChatSessionSearchCriteria(user_id=user_id)
        )

        if existing_chats:
            # Return the most recently created chat
            most_recent_chat = max(existing_chats, key=lambda c: c.created_at)
            self._logger.info(
                f"Retrieved existing chat session {most_recent_chat.id} for user {user_id}"
            )
            return most_recent_chat.id

        # No existing chats, create a new one
        async with self.tx_factory.create() as tx:
            data = ChatSession(
                title=title or "New Chat",
                user_id=user_id,
            )
            created_id = await self.chat_session_repo.create(
                data=data,
                tx=tx,
            )

        self._logger.info(f"Created new chat session {created_id} for user {user_id}")

        return created_id

    async def get_chat_messages(
        self, criteria: ChatMessageSearchCriteria
    ) -> List[ChatMessage]:
        await self._get_owned_chat(criteria.session_id)
        return await self.chat_message_repo.list_by(criteria)
