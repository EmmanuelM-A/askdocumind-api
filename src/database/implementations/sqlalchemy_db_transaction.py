"""
SQLAlchemy implementation of the ORM-agnostic transaction contracts.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.interfaces.db_transactions import DBTransaction, DBTransactionFactory
from src.database.session import DatabaseSessionManager
from src.exceptions.custom import database_error


class _SQLAlchemyDBTransaction(DBTransaction):
    """Transaction adapter backed by a SQLAlchemy ``AsyncSession``.

    Instances are single-use: once committed, rolled back, or closed,
    create a new instance via the factory for the next transaction.
    """

    def __init__(self, session_manager: DatabaseSessionManager) -> None:
        self._session_manager: DatabaseSessionManager = session_manager
        self._session: AsyncSession | None = None
        self._active = False
        self._finished = False

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def session(self) -> AsyncSession:
        """Expose the native SQLAlchemy session for concrete repositories."""
        if self._session is None:
            raise database_error(
                message="Database session is not available",
                error_code="NO_ACTIVE_SESSION_DETECTED",
            )
        return self._session

    async def _ensure_session(self) -> AsyncSession:
        if self._finished:
            raise database_error(
                message=(
                    "Transaction has already been committed, rolled back, "
                    "or closed. Create a new transaction instead of reusing "
                    "this instance."
                ),
                error_code="TRANSACTION_ALREADY_FINISHED",
            )

        if self._session is None:
            if self._session_manager.session_maker is None:
                raise database_error(
                    message="Database connection has not been initialized",
                    error_code="CONNECTION_NOT_INITIALIZED",
                )
            self._session = self._session_manager.session_maker()
            self._active = True

        assert self._session is not None

        return self._session

    async def add(self, entity: Any) -> None:
        session = await self._ensure_session()
        session.add(entity)

    async def add_all(self, entities: list[Any]) -> None:
        if not entities:
            return
        session = await self._ensure_session()
        session.add_all(entities)

    async def execute(
        self, statement: Any, parameters: Any = None, **kwargs: Any
    ) -> Any:
        session = await self._ensure_session()
        return await session.execute(statement, parameters, **kwargs)

    async def flush(self) -> None:
        session = await self._ensure_session()
        await session.flush()

    async def commit(self) -> None:
        session = await self._ensure_session()
        await session.commit()
        self._active = False
        self._finished = True

    async def rollback(self) -> None:
        if self._session is None:
            return
        await self._session.rollback()
        self._active = False
        self._finished = True

    async def close(self) -> None:
        if self._session is None:
            return
        await self._session.close()
        self._session = None
        self._active = False
        self._finished = True

    async def __aenter__(self) -> DBTransaction:
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is not None:
                await self.rollback()
            elif self._session is not None:
                await self.commit()
        finally:
            await self.close()


class DBTransactionFactoryImpl(DBTransactionFactory):
    """Factory for creating SQLAlchemy transaction adapters."""

    def __init__(self, session_manager: DatabaseSessionManager) -> None:
        self._session_manager = session_manager

    def create(self) -> DBTransaction:
        return _SQLAlchemyDBTransaction(session_manager=self._session_manager)
