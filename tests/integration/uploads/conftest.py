"""
Shared fixtures for the upload integration tests: chat sessions committed
through the real session manager. The S3 bucket fixtures live in the root
conftest.
"""

import pytest_asyncio
from sqlalchemy import delete

import src.database.models  # noqa: F401  registers every model for the mappers
from src.auth.models.user import User
from src.chat_session.models.chat_session import ChatSession


@pytest_asyncio.fixture
async def new_chat_session(manager):
    """Create committed chat sessions; their users are deleted afterwards."""
    users = []

    async def _create():
        async with manager.get_session() as session:
            user = User()
            session.add(user)
            await session.flush()
            chat_session = ChatSession(user_id=user.id, title="test")
            session.add(chat_session)
            await session.flush()
        users.append(user.id)
        return chat_session.id

    yield _create

    async with manager.get_session() as session:
        await session.execute(delete(User).where(User.id.in_(users)))
