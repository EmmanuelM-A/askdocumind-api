"""
Shared fixtures for all e2e tests. Real app, real DB, real auth - nothing
mocked. Route-specific fixtures live in each subpackage's own conftest.py.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.utils.session_manager import TokenManager, get_token_manager
from src.components.retrieval.embedder import Embedder
from src.config.configs import settings
from src.database.models import ChatSession, Document, DocumentChunk, User
from src.database.repository.database_repository_factory import get_database_repository
from src.database.repository.sqlalchemy.chat_message_repository import (
    ChatMessageRepository,
)
from src.database.repository.sqlalchemy.chat_session_repository import (
    ChatSessionRepository,
)
from src.database.repository.sqlalchemy.document_chunk_repository import (
    DocumentChunkRepository,
)
from src.database.repository.sqlalchemy.document_repository import DocumentRepository
from src.database.repository.sqlalchemy.user_repository import UserRepository


@pytest.fixture(scope="module")
def app_client():
    """Real app, wired up via ASGI lifespan (connects the shared DB connection on startup)."""
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def user_repo() -> UserRepository:
    return get_database_repository("USER")


@pytest.fixture
def chat_session_repo() -> ChatSessionRepository:
    return get_database_repository("CHAT_SESSION")


@pytest.fixture
def chat_message_repo() -> ChatMessageRepository:
    return get_database_repository("CHAT_MESSAGE")


@pytest.fixture
def document_repo() -> DocumentRepository:
    return get_database_repository("DOCUMENT")


@pytest.fixture
def document_chunk_repo() -> DocumentChunkRepository:
    return get_database_repository("DOCUMENT_CHUNK")


@pytest.fixture(scope="module")
def embedder() -> Embedder:
    """Real Embedder, shared across tests that seed chunks with real embeddings."""
    return Embedder()


@pytest.fixture
def token_manager() -> TokenManager:
    return get_token_manager()


@pytest.fixture
def created_user_ids() -> List[UUID]:
    return []


@pytest_asyncio.fixture(autouse=True)
async def cleanup_users(user_repo: UserRepository, created_user_ids: List[UUID]):
    """Deletes every user a test registered; owned chats/messages/documents/chunks cascade."""
    yield
    if created_user_ids:
        await user_repo.delete_many(created_user_ids)


@pytest.fixture
def seed_user(user_repo: UserRepository, created_user_ids: List[UUID]):
    """Factory: inserts a real User row."""

    async def _seed(last_seen_at: Optional[datetime] = None) -> UUID:
        user = User(last_seen_at=last_seen_at or datetime.now(timezone.utc))
        user_id = await user_repo.create(user)
        created_user_ids.append(user_id)
        return user_id

    return _seed


@pytest.fixture
def seed_chat_session(chat_session_repo: ChatSessionRepository):
    """Factory: inserts a real ChatSession row for the given owner."""

    async def _seed(user_id: UUID, title: str = "Test Chat") -> UUID:
        session = ChatSession(title=title, user_id=user_id)
        return await chat_session_repo.create(data=session)

    return _seed


@pytest.fixture
def seed_chunk(
    document_repo: DocumentRepository,
    document_chunk_repo: DocumentChunkRepository,
    embedder: Embedder,
):
    """Factory: creates a real Document + DocumentChunk with a real embedding."""

    async def _seed(chat_id: UUID, text: str, filename: str = "seeded.txt") -> UUID:
        doc_id = await document_repo.create(
            Document(session_id=chat_id, filename=filename, file_size=len(text.encode()))
        )
        chunk = DocumentChunk(
            document_id=doc_id,
            chat_session_id=chat_id,
            chunk_text=text,
            embedding=embedder.embed_query(text),
        )
        return await document_chunk_repo.create(data=chunk)

    return _seed


@pytest.fixture
def auth_cookie(token_manager: TokenManager):
    """Factory: builds a Cookie header dict for a given user id."""

    def _cookie(user_id: UUID) -> dict:
        token = token_manager.create_token(user_id)
        return {"Cookie": f"{settings.auth.COOKIE_NAME}={token}"}

    return _cookie
