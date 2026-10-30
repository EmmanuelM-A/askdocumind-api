"""
Shared fixtures for the chat session integration tests: a chat session with
a message, a document, an embedding and a stored file, all committed through
the real session manager. The S3 bucket fixtures live in the root conftest.
"""

import hashlib
import uuid
from dataclasses import dataclass

import pytest_asyncio
from sqlalchemy import delete

import src.database.models  # noqa: F401  registers every model for the mappers
from src.auth.models.user import User
from src.chat_session.domain.chat import ChatMessageRole
from src.chat_session.models.chat_message import ChatMessage
from src.chat_session.models.chat_session import ChatSession
from src.config.configs import settings
from src.rag.models.chunk_embedding import ChunkEmbedding
from src.uploads.domain.document import DocumentStatus
from src.uploads.models.document import Document
from src.uploads.storage.keys import document_object_key

CONTENT = b"The quick brown fox jumps over the lazy dog."


@dataclass(frozen=True)
class SeededChat:
    user_id: uuid.UUID
    chat_session_id: uuid.UUID
    object_key: str


@pytest_asyncio.fixture
async def seed_chat(manager, object_storage):
    """Create committed chat sessions; their users are deleted afterwards."""
    users = []

    async def _seed(user_id=None):
        async with manager.get_session() as session:
            if user_id is None:
                user = User()
                session.add(user)
                await session.flush()
                user_id = user.id
                users.append(user_id)

            chat_session = ChatSession(user_id=user_id, title="test")
            session.add(chat_session)
            await session.flush()

            document_id = uuid.uuid4()
            object_key = document_object_key(chat_session.id, document_id)
            session.add_all(
                [
                    ChatMessage(
                        chat_session_id=chat_session.id,
                        role=ChatMessageRole.USER,
                        content="hi",
                        sources=[],
                    ),
                    Document(
                        id=document_id,
                        chat_session_id=chat_session.id,
                        original_filename="notes.txt",
                        object_key=object_key,
                        content_type="text/plain",
                        size_bytes=len(CONTENT),
                        checksum=hashlib.sha256(CONTENT).hexdigest(),
                        status=DocumentStatus.COMPLETED,
                    ),
                ]
            )
            await session.flush()
            session.add(
                ChunkEmbedding(
                    document_id=document_id,
                    chat_session_id=chat_session.id,
                    chunk_index=0,
                    chunk_text=CONTENT.decode(),
                    embedding=[0.1] * settings.rag.EMBEDDING_DIMENSIONS,
                )
            )

        object_storage.save(object_key, CONTENT)
        return SeededChat(user_id, chat_session.id, object_key)

    yield _seed

    async with manager.get_session() as session:
        await session.execute(delete(User).where(User.id.in_(users)))
