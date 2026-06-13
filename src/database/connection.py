"""
Handles connections to the database and session management.
"""

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.errors.custom_exceptions import database_error
from src.logger.base_logger import BaseLogger
from src.config.configs import settings

logger = BaseLogger(__name__)


class DatabaseConnection:
    """
    This class handles connection pooling, session management, and cleanup.
    """

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or str(
            settings.database.DATABASE_URL.get_secret_value()
        )
        self.engine = None
        self.session_maker = None

        if not self.database_url:
            raise database_error(
                "DATABASE_URL is not configured or invalid.", "MISSING_DATABASE_URL"
            )

    async def connect(self):
        """Create the async SQLAlchemy engine and session factory."""

        if self.engine is not None:
            logger.warning("Database connection already exists.")
            return

        try:
            self.engine = create_async_engine(
                url=self.database_url,
                echo=settings.database.DB_ECHO,
                pool_pre_ping=settings.database.DB_IS_POOL_PRE_PING_ENABLED,
                pool_size=settings.database.DB_POOL_SIZE,
                max_overflow=settings.database.DB_MAX_OVERFLOW,
                pool_timeout=settings.database.DB_POOL_TIMEOUT_SECS,
            )
            self.session_maker = async_sessionmaker(
                bind=self.engine, expire_on_commit=False, autoflush=False
            )
        except Exception as e:
            raise database_error(
                message="Failed to connect to the database during initialization.",
                error_code="DB_CONNECTION_ERROR",
                stack_trace=str(e),
            )

        logger.info("Database connected successfully.")

    async def disconnect(self):
        """Dispose the engine and close connections."""

        if self.engine:
            await self.engine.dispose()
            logger.info("Database disconnected successfully.")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[Any, Any]:
        """Get a new database session."""

        if not self.session_maker:
            raise database_error(
                "No session available because the database has not been connected.",
                "NO_DB_CONNECTION_DETECTED",
            )

        session = self.session_maker()

        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()
    
    async def ping_database(self) -> None:
        """Ping the database to check connectivity."""
        async with self.get_session() as session:
            await session.execute("SELECT 1")


# Global database connection instance
_database_connection: Optional[DatabaseConnection] = None


def get_database_connection() -> DatabaseConnection:
    """
    Returns the global singleton instance of the DatabaseConnection class.
    """

    global _database_connection

    if _database_connection is None:
        _database_connection = DatabaseConnection()

    return _database_connection
