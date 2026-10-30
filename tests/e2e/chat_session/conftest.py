"""
Shared fixtures for the chat session endpoint e2e tests.

Requests go through the real app: its middleware, cookie authentication,
rate limits, routers, Postgres and an S3 bucket. Rows are committed and
removed through their users afterwards.
"""

import hashlib
import uuid
from dataclasses import dataclass

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

import src.database.models  # noqa: F401  registers every model for the mappers
from src.app import create_app
from src.auth.models.user import User
from src.auth.services.token_service import create_anonymous_token
from src.chat_session.domain.chat import ChatMessageRole
from src.chat_session.models.chat_message import ChatMessage
from src.chat_session.models.chat_session import ChatSession
from src.config.configs import settings
from src.rag.models.chunk_embedding import ChunkEmbedding
from src.uploads.domain.document import DocumentStatus
from src.uploads.models.document import Document
from src.uploads.storage.dependencies import get_object_storage
from src.uploads.storage.keys import document_object_key

CONTENT = b"The quick brown fox jumps over the lazy dog."


@dataclass(frozen=True)
class AnonymousUser:
    user_id: uuid.UUID
    headers: dict[str, str]


def cookie_headers(user_id):
    token = create_anonymous_token(user_id)
    return {"Cookie": f"{settings.auth.ANONYMOUS_COOKIE_NAME}={token}"}


@pytest.fixture
def app(manager, object_storage):
    # The lifespan is not run by the test transport, so set its state here.
    app = create_app()
    app.state.session_manager = manager
    app.dependency_overrides[get_object_storage] = lambda: object_storage
    return app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="https://test") as http:
        yield http


@pytest_asyncio.fixture
async def make_user(manager):
    """Commit a user with no chat sessions; deleted with their rows afterwards."""
    users = []

    async def _make():
        async with manager.get_session() as session:
            user = User()
            session.add(user)
            await session.flush()
        users.append(user.id)
        return AnonymousUser(user_id=user.id, headers=cookie_headers(user.id))

    yield _make

    async with manager.get_session() as session:
        await session.execute(delete(User).where(User.id.in_(users)))


@pytest_asyncio.fixture
async def user(make_user):
    return await make_user()


@pytest.fixture
def make_chat(manager):
    async def _make(user_id, title="test", created_at=None):
        async with manager.get_session() as session:
            chat_session = ChatSession(user_id=user_id, title=title)
            if created_at is not None:
                chat_session.created_at = created_at
            session.add(chat_session)
            await session.flush()
        return chat_session.id

    return _make


@pytest.fixture
def seed_message(manager):
    async def _seed(
        chat_session_id, content, created_at, role=ChatMessageRole.USER, sources=()
    ):
        async with manager.get_session() as session:
            message = ChatMessage(
                chat_session_id=chat_session_id,
                role=role,
                content=content,
                sources=list(sources),
                created_at=created_at,
            )
            session.add(message)
            await session.flush()
        return message.id

    return _seed


@pytest.fixture
def seed_document(manager, object_storage):
    """Commit a processed document with one embedding, and store its file."""

    async def _seed(chat_session_id):
        document_id = uuid.uuid4()
        object_key = document_object_key(chat_session_id, document_id)
        async with manager.get_session() as session:
            session.add(
                Document(
                    id=document_id,
                    chat_session_id=chat_session_id,
                    original_filename=f"{uuid.uuid4().hex[:8]}.txt",
                    object_key=object_key,
                    content_type="text/plain",
                    size_bytes=len(CONTENT),
                    checksum=hashlib.sha256(CONTENT).hexdigest(),
                    status=DocumentStatus.COMPLETED,
                )
            )
            await session.flush()
            session.add(
                ChunkEmbedding(
                    document_id=document_id,
                    chat_session_id=chat_session_id,
                    chunk_index=0,
                    chunk_text=CONTENT.decode(),
                    embedding=[0.1] * settings.rag.EMBEDDING_DIMENSIONS,
                )
            )
        object_storage.save(object_key, CONTENT)
        return object_key

    return _seed


@pytest.fixture
def read_chats(manager):
    """Read a user's committed chat sessions, newest first."""

    async def _read(user_id):
        async with manager.get_session() as session:
            result = await session.execute(
                select(ChatSession)
                .where(ChatSession.user_id == user_id)
                .order_by(ChatSession.created_at.desc())
            )
            return list(result.scalars().all())

    return _read


@pytest.fixture
def count_rows(manager):
    """Count a chat session's committed rows in each table it owns."""

    async def _count(chat_session_id):
        counts = {}
        async with manager.get_session() as session:
            for model in (ChatSession, ChatMessage, Document, ChunkEmbedding):
                column = model.id if model is ChatSession else model.chat_session_id
                counts[model.__tablename__] = (
                    await session.execute(
                        select(func.count())
                        .select_from(model)
                        .where(column == chat_session_id)
                    )
                ).scalar_one()
        return counts

    return _count
