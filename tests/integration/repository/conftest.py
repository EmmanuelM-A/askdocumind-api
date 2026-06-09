"""
Global test fixtures and configurations for the repository tests
"""

from src.database.connection import DatabaseConnection
from src.database.models import User, ChatSession

import pytest_asyncio

# ========================= COMMON DATABASE FIXTURES =========================


@pytest_asyncio.fixture
async def db_connection():
    """Provide a database connection for tests."""
    conn = DatabaseConnection()
    await conn.connect()
    yield conn
    await conn.disconnect()


@pytest_asyncio.fixture
async def test_user(db_connection):
    """Create a test user for document ownership."""
    user = User()
    async with db_connection.get_session() as session:
        session.add(user)
        await session.commit()
    try:
        yield user
    finally:
        from sqlalchemy import delete

        async with db_connection.get_session() as session:
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()


@pytest_asyncio.fixture
async def test_chat_session(db_connection, test_user):
    """Create a test chat session."""
    chat_session = ChatSession(user_id=test_user.id)
    async with db_connection.get_session() as db_session:
        db_session.add(chat_session)
        await db_session.commit()
    try:
        yield chat_session
    finally:
        from sqlalchemy import delete

        async with db_connection.get_session() as db_session:
            await db_session.execute(
                delete(ChatSession).where(ChatSession.id == chat_session.id)
            )
            await db_session.commit()
