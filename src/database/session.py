"""
Manages the SQLAlchemy async engine and session lifecycle.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.config.configs import settings
from src.exceptions import database_error

_logger = logging.getLogger(__name__)


class DatabaseSessionManager:
    """
    Owns the engine and creates sessions.
    """

    def __init__(self, database_url: str) -> None:
        if settings.database.DB_USE_NULL_POOL:
            # No idle connections are kept, so the pool settings don't apply
            pool_options: dict[str, Any] = {"poolclass": NullPool}
        else:
            pool_options = {
                "pool_pre_ping": settings.database.DB_IS_POOL_PRE_PING_ENABLED,
                "pool_size": settings.database.DB_POOL_SIZE,
                "max_overflow": settings.database.DB_MAX_OVERFLOW,
                "pool_timeout": settings.database.DB_POOL_TIMEOUT_SECS,
                "pool_recycle": 1800,
            }

        self.engine: AsyncEngine = create_async_engine(
            database_url, echo=settings.database.DB_ECHO, **pool_options
        )
        self.session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine, expire_on_commit=False, autoflush=False
        )

    async def connect(self) -> None:
        """Verify the database is reachable. Call once at startup."""
        try:
            await self.ping()
            _logger.info("Database connected successfully")
        except SQLAlchemyError as e:
            raise database_error(
                message="Failed to connect to the database during initialization",
                error_code="DB_CONNECTION_ERROR",
                cause=e,
            ) from e

    async def disconnect(self) -> None:
        """Close all pooled connections. Call once at shutdown."""
        await self.engine.dispose()
        _logger.info("Database disconnected successfully")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a session. Commits on success, rolls back on error, then closes."""
        async with self.session_maker.begin() as session:
            yield session

    async def ping(self) -> None:
        """Run a trivial query to check connectivity."""
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
