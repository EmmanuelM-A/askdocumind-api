"""
Shared fixtures for the upload endpoint e2e tests.

Requests go through the real app: its middleware, cookie authentication,
routers, Postgres and an S3 bucket. Rows are committed and removed through
their users afterwards. Only the ingestion runner is mocked, because a real
run calls the paid embedding API; it has its own integration tests.
"""

import hashlib
import uuid
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

import src.database.models  # noqa: F401  registers every model for the mappers
from src.app import create_app
from src.auth.models.user import User
from src.auth.services.token_service import create_anonymous_token
from src.chat_session.models.chat_session import ChatSession
from src.config.configs import settings
from src.uploads.domain.document import DocumentStatus
from src.uploads.models.document import Document
from src.uploads.services.ingestion_service import IngestionRunner
from src.uploads.storage.dependencies import get_object_storage

CONTENT = b"The quick brown fox jumps over the lazy dog."


@dataclass(frozen=True)
class Owner:
    user_id: uuid.UUID
    chat_session_id: uuid.UUID
    headers: dict[str, str]


@pytest.fixture
def runner():
    return MagicMock(spec=IngestionRunner)


@pytest.fixture
def app(manager, object_storage, runner):
    # The lifespan is not run by the test transport, so set its state here.
    app = create_app()
    app.state.session_manager = manager
    app.state.ingestion_runner = runner
    app.dependency_overrides[get_object_storage] = lambda: object_storage
    return app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="https://test") as http:
        yield http


@pytest_asyncio.fixture
async def make_owner(manager):
    """Commit a chat session, for a new user unless one is given."""
    users = []

    async def _make(user_id=None):
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
        token = create_anonymous_token(user_id)
        return Owner(
            user_id=user_id,
            chat_session_id=chat_session.id,
            headers={"Cookie": f"{settings.auth.ANONYMOUS_COOKIE_NAME}={token}"},
        )

    yield _make

    async with manager.get_session() as session:
        await session.execute(delete(User).where(User.id.in_(users)))


@pytest_asyncio.fixture
async def owner(make_owner):
    return await make_owner()


@pytest_asyncio.fixture
async def seed_document(manager, object_storage):
    """Commit a document directly, with its file stored unless told not to."""

    async def _seed(
        chat_session_id,
        filename=None,
        status=DocumentStatus.UPLOADED,
        store_file=True,
    ):
        key = f"{chat_session_id}/{uuid.uuid4()}"
        if store_file:
            object_storage.save(key, CONTENT)
        async with manager.get_session() as session:
            document = Document(
                chat_session_id=chat_session_id,
                original_filename=filename or f"{uuid.uuid4().hex[:8]}.txt",
                object_key=key,
                content_type="text/plain",
                size_bytes=len(CONTENT),
                checksum=hashlib.sha256(CONTENT).hexdigest(),
                status=status,
                error_message="boom" if status is DocumentStatus.FAILED else None,
            )
            session.add(document)
            await session.flush()
        return document

    return _seed


@pytest.fixture
def read_documents(manager):
    """Read a chat session's committed documents, newest first."""

    async def _read(chat_session_id):
        async with manager.get_session() as session:
            result = await session.execute(
                select(Document)
                .where(Document.chat_session_id == chat_session_id)
                .order_by(Document.created_at.desc())
            )
            return list(result.scalars().all())

    return _read
