import asyncio
import logging
from uuid import UUID

from src.auth.repository.user_repository import UserRepository
from src.chat_session.models.chat_session import ChatSession
from src.chat_session.models.mapper import ViewableChatSession, ViewableChatMessage
from src.chat_session.repository.chat_message_repository import (
    ChatMessageRepository,
    ChatMessageSearchFilter,
)
from src.chat_session.repository.chat_message_repository_impl import (
    ChatMessageRepositoryImpl,
)
from src.chat_session.repository.chat_session_repository import ChatSessionRepository
from src.chat_session.repository.chat_session_repository_impl import (
    ChatSessionRepositoryImpl,
)
from src.chat_session.schemas.chat_session import CreateChatSession
from src.database.session import DatabaseSessionManager
from src.exceptions import unprocessable_content_error
from src.rag.repository.chunk_embedding_repository_impl import (
    ChunkEmbeddingRepositoryImpl,
)
from src.shared.utils import BaseService
from src.uploads.repository.document_repository_impl import DocumentRepositoryImpl
from src.uploads.storage.object_storage import ObjectStorage

_logger = logging.getLogger(__name__)

# TODO: add to .env and configs
_MAX_CHATS_PER_USER = 5  # Maximum number of chat sessions allowed per user


class ChatSessionService(BaseService):

    def __init__(
        self,
        user_repository: UserRepository,
        chat_session_repository: ChatSessionRepository,
        chat_message_repository: ChatMessageRepository,
        object_storage: ObjectStorage,
        session_manager: DatabaseSessionManager,
    ) -> None:
        super().__init__(user_repository, chat_session_repository)
        self._chat_message_repository = chat_message_repository
        self._object_storage = object_storage
        self._session_manager = session_manager

    async def create_new_chat_session(
        self, user_id: UUID, data: CreateChatSession
    ) -> ViewableChatSession:
        """
        Create a new chat session for the user if they haven't exceeded the
        maximum allowed sessions.
        """
        await self._verify_user_exists(user_id)

        total_chats = await self._chat_session_repository.count(user_id)

        if total_chats >= _MAX_CHATS_PER_USER:
            raise unprocessable_content_error(
                message="The user has reached the maximum number of chat sessions allowed.",
                error_code="MAX_CHAT_SESSIONS_REACHED",
            )

        _logger.debug(
            f"The user '%s' has not exceeding the maximum number of chat "
            f"sessions allowed. Proceeding..."
        )

        entity = ChatSession(user_id=user_id, title=data.title)

        created = await self._chat_session_repository.create(entity)

        _logger.debug("New chat session created for the user '%s'", user_id)

        return created.viewable()

    async def initialize_chat_session(
        self, user_id: UUID, data: CreateChatSession
    ) -> ViewableChatSession:
        """
        Initialize a chat session for the user. If a chat session already
        exists, return it; otherwise, create a new one.
        """
        await self._verify_user_exists(user_id)

        chat_session = await self._chat_session_repository.get_by_user_id(user_id)

        if chat_session is None:
            _logger.debug(
                "No chat session exists for the user '%s'. Creating a " "new one...",
                user_id,
            )
            return await self.create_new_chat_session(user_id, data)

        return chat_session.viewable()

    async def get_chat_session(
        self, user_id: UUID, chat_session_id: UUID
    ) -> ViewableChatSession:
        """
        Retrieve a chat session by its ID, ensuring that the user has access
        to it.
        """
        await self._verify_user_exists(user_id)

        chat_session = await self._verify_user_owns_chat_session(
            user_id, chat_session_id
        )

        return chat_session.viewable()

    async def delete_chat_session(self, user_id: UUID, chat_session_id: UUID) -> None:
        """
        Delete a chat session by its ID, ensuring that the user has access
        to it.
        """
        await self._verify_user_exists(user_id)
        await self._verify_user_owns_chat_session(user_id, chat_session_id)

        prefix = f"{chat_session_id}/"

        await asyncio.to_thread(self._object_storage.delete_prefix, prefix)

        async with self._session_manager.get_session() as session:
            chunk_repository = ChunkEmbeddingRepositoryImpl(session)
            messages_repository = ChatMessageRepositoryImpl(session)
            documents_repository = DocumentRepositoryImpl(session)
            chat_session_repository = ChatSessionRepositoryImpl(session)

            await chunk_repository.delete_by_chat_session(chat_session_id)
            await messages_repository.delete_all(chat_session_id)
            await documents_repository.delete_by_chat_session(chat_session_id)
            await chat_session_repository.delete(chat_session_id)

            await session.commit()

        try:
            await asyncio.to_thread(self._object_storage.delete_prefix, prefix)
        except Exception:
            _logger.exception(
                "Second file cleanup failed for session '%s'", chat_session_id
            )

        _logger.debug(
            "Chat session '%s' deleted for user '%s'", chat_session_id, user_id
        )

    async def get_chat_session_messages(
        self, user_id: UUID, chat_session_id: UUID
    ) -> list[ViewableChatMessage]:
        """
        Retrieve the messages for a chat session, ensuring that the user has access to it.
        """
        await self._verify_user_exists(user_id)
        await self._verify_user_owns_chat_session(user_id, chat_session_id)

        messages = await self._chat_message_repository.list_by_criteria(
            user_id=user_id,
            criteria=ChatMessageSearchFilter(chat_session_id=chat_session_id),
        )

        return [message.viewable() for message in messages]
