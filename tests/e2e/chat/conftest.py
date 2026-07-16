"""
Real (non-mocked) fixtures for e2e tests of the chat session endpoints.

These fixtures run the real FastAPI app (with lifespan, so the real DB
connection is established/torn down), talk to the real database, and use
the real TokenManager for signing session cookies - mirroring
tests/e2e/auth/conftest.py.

Note: the app's own DB connection (wired up via ASGI lifespan inside
TestClient) lives on TestClient's internal thread/event loop. asyncpg
connections are bound to the loop they were created on, so test-side
seeding/verification queries must NOT reuse that connection from the
test's own event loop - instead we open a second, independent
DatabaseConnection scoped to each test.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import delete

from src.api.app import create_app
from src.api.utils.session_manager import TokenManager, get_token_manager
from src.config.configs import settings
from src.database.connection import DatabaseConnection
from src.database.models import ChatSession, User
from src.database.repository.sqlalchemy.chat_message_repository import (
    ChatMessageRepository,
)
from src.database.repository.sqlalchemy.chat_session_repository import (
    ChatSessionRepository,
)
from src.database.repository.sqlalchemy.user_repository import UserRepository


@pytest.fixture(scope="module")
def app_client():
    """Real app + real DB connection, wired up via ASGI lifespan."""
    with TestClient(create_app()) as client:
        yield client


@pytest_asyncio.fixture
async def db_connection():
    """Independent DB connection for test-side seeding/verification,
    bound to this test's own event loop."""
    conn = DatabaseConnection()
    await conn.connect()
    yield conn
    await conn.disconnect()


@pytest.fixture
def user_repo(db_connection: DatabaseConnection) -> UserRepository:
    return UserRepository(connection=db_connection)


@pytest.fixture
def chat_session_repo(db_connection: DatabaseConnection) -> ChatSessionRepository:
    return ChatSessionRepository(connection=db_connection)


@pytest.fixture
def chat_message_repo(db_connection: DatabaseConnection) -> ChatMessageRepository:
    return ChatMessageRepository(connection=db_connection)


@pytest.fixture
def token_manager() -> TokenManager:
    return get_token_manager()


@pytest.fixture
def created_user_ids() -> List[UUID]:
    return []


@pytest_asyncio.fixture(autouse=True)
async def cleanup_users(db_connection: DatabaseConnection, created_user_ids: List[UUID]):
    """Deletes every user row a test registered as created, after the test
    runs. Chat sessions (and their messages) owned by that user are removed
    automatically via ON DELETE CASCADE, so no separate chat cleanup list is
    needed. Autouse so every test in this package gets cleanup for free."""
    yield

    if not created_user_ids:
        return

    async with db_connection.get_session() as session:
        await session.execute(delete(User).where(User.id.in_(created_user_ids)))
        await session.commit()


@pytest.fixture
def seed_user(user_repo: UserRepository, created_user_ids: List[UUID]):
    """Factory fixture: inserts a real User row via the real repository."""

    async def _seed(last_seen_at: Optional[datetime] = None) -> UUID:
        user = User(last_seen_at=last_seen_at or datetime.now(timezone.utc))
        user_id = await user_repo.create(user)
        created_user_ids.append(user_id)
        return user_id

    return _seed


@pytest.fixture
def seed_chat_session(chat_session_repo: ChatSessionRepository):
    """Factory fixture: inserts a real ChatSession row for the given owner.
    Cleanup is implicit via the owning user's cascade delete."""

    async def _seed(user_id: UUID, title: str = "Test Chat") -> UUID:
        session = ChatSession(title=title, user_id=user_id)
        return await chat_session_repo.create(data=session)

    return _seed


@pytest.fixture
def auth_cookie(token_manager: TokenManager):
    """Factory fixture: builds a {cookie_name: token} dict for a given user id."""

    def _cookie(user_id: UUID) -> dict:
        return {settings.auth.COOKIE_NAME: token_manager.create_token(user_id)}

    return _cookie
