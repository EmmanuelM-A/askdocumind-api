"""
Unit tests for the connection pool choice in DatabaseSessionManager.
Creating the engine doesn't connect, so no database is needed.
"""

import pytest
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from src.config.configs import settings
from src.database.session import DatabaseSessionManager

_URL = "postgresql+asyncpg://user:secret@localhost:5432/db"


@pytest.mark.asyncio
async def test_null_pool_keeps_no_idle_connections(monkeypatch):
    monkeypatch.setattr(settings.database, "DB_USE_NULL_POOL", True)

    manager = DatabaseSessionManager(_URL)

    assert isinstance(manager.engine.pool, NullPool)
    await manager.disconnect()


@pytest.mark.asyncio
async def test_queue_pool_is_the_default(monkeypatch):
    monkeypatch.setattr(settings.database, "DB_USE_NULL_POOL", False)

    manager = DatabaseSessionManager(_URL)

    assert isinstance(manager.engine.pool, AsyncAdaptedQueuePool)
    assert manager.engine.pool.size() == settings.database.DB_POOL_SIZE
    await manager.disconnect()
