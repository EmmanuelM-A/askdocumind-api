"""
Real (non-mocked) fixtures for e2e tests of the anonymous-session endpoints.

These fixtures run the real FastAPI app (with lifespan, so the real DB
connection is established/torn down), talk to the real database, and use
the real TokenManager for signing/decoding session cookies.

Note: the app's own DB connection (wired up via ASGI lifespan inside
TestClient) lives on TestClient's internal thread/event loop. asyncpg
connections are bound to the loop they were created on, so test-side
seeding/verification queries must NOT reuse that connection from the
test's own event loop — instead we open a second, independent
DatabaseConnection scoped to each test, matching the pattern already used
in tests/integration/repository/conftest.py.
"""

from datetime import datetime, timezone
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import delete

from src.api.app import create_app
from src.api.utils.session_manager import TokenManager, get_token_manager
from src.database.connection import DatabaseConnection
from src.database.models import User
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
def token_manager() -> TokenManager:
    return get_token_manager()


@pytest.fixture
def created_user_ids() -> list[UUID]:
    return []


@pytest_asyncio.fixture(autouse=True)
async def cleanup_users(db_connection: DatabaseConnection, created_user_ids: list[UUID]):
    """Deletes every user row a test registered as created, after the test runs.
    Autouse so every test in this package gets cleanup without needing to
    explicitly request the fixture."""
    yield

    if not created_user_ids:
        return

    async with db_connection.get_session() as session:
        await session.execute(delete(User).where(User.id.in_(created_user_ids)))
        await session.commit()


@pytest.fixture
def seed_user(user_repo: UserRepository, created_user_ids: list[UUID]):
    """Factory fixture: inserts a real User row via the real repository."""

    async def _seed(last_seen_at: datetime | None = None) -> UUID:
        user = User(last_seen_at=last_seen_at or datetime.now(timezone.utc))
        user_id = await user_repo.create(user)
        created_user_ids.append(user_id)
        return user_id

    return _seed
