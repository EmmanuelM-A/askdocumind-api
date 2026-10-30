"""
Fixtures shared by the e2e tests: committed users with their session cookies,
their chat sessions, and an HTTP client for the folder's `app` fixture.
"""

import uuid
from dataclasses import dataclass

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

import src.database.models  # noqa: F401  registers every model for the mappers
from src.auth.models.user import User
from src.auth.services.token_service import create_anonymous_token
from src.chat_session.models.chat_session import ChatSession
from src.config.configs import settings


@dataclass(frozen=True)
class AnonymousUser:
    user_id: uuid.UUID
    headers: dict[str, str]


def cookie_headers(user_id):
    token = create_anonymous_token(user_id)
    return {"Cookie": f"{settings.auth.ANONYMOUS_COOKIE_NAME}={token}"}


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
