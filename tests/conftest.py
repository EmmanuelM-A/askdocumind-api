"""
Global fixtures for pytest.
"""

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.configs import settings
from src.database.session import DatabaseSessionManager
from src.middleware.rate_limiter import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Stop rate limit counts leaking between tests."""
    limiter.reset()


@pytest_asyncio.fixture
async def manager():
    url = settings.database.DATABASE_URL.get_secret_value()

    if not url:
        pytest.skip("DATABASE_URL is not set")

    session_manager = DatabaseSessionManager(url)

    yield session_manager

    await session_manager.disconnect()


@pytest_asyncio.fixture
async def session(manager) -> AsyncGenerator[AsyncSession]:
    async with manager.engine.connect() as conn:
        outer = await conn.begin()
        async with AsyncSession(
            bind=conn,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        ) as db_session:
            yield db_session
        await outer.rollback()
