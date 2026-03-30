"""SQLAlchemy implementation of the ORM-agnostic transaction contracts."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import DatabaseConnection
from src.database.repository.interfaces.db_transaction import (
	DBTransaction,
	DBTransactionFactory,
)
from src.errors.custom_exceptions import database_error


class SQLAlchemyDBTransaction(DBTransaction):
	"""Transaction adapter backed by a SQLAlchemy ``AsyncSession``."""

	def __init__(self, connection: DatabaseConnection) -> None:
		self._connection = connection
		self._session: Optional[AsyncSession] = None
		self._active = False

	@property
	def is_active(self) -> bool:
		return self._active

	@property
	def session(self) -> AsyncSession:
		"""Expose the native SQLAlchemy session for concrete repositories."""
		if self._session is None:
			raise database_error(
				message="Database transaction has not been started.",
				error_code="DB_TRANSACTION_NOT_STARTED",
			)
		return self._session

	async def _ensure_session(self) -> AsyncSession:
		if self._session is None:
			if self._connection.session_maker is None:
				raise database_error(
					message="No session available because the database has not been connected.",
					error_code="NO_DB_CONNECTION_DETECTED",
				)
			self._session = self._connection.session_maker()
			self._active = True
		return self._session

	async def add(self, entity: Any) -> None:
		session = await self._ensure_session()
		session.add(entity)

	async def add_all(self, entities: list[Any]) -> None:
		if not entities:
			return
		session = await self._ensure_session()
		session.add_all(entities)

	async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
		session = await self._ensure_session()
		return await session.execute(statement, *args, **kwargs)

	async def flush(self) -> None:
		session = await self._ensure_session()
		await session.flush()

	async def commit(self) -> None:
		session = await self._ensure_session()
		await session.commit()
		self._active = False

	async def rollback(self) -> None:
		if self._session is None:
			return
		await self._session.rollback()
		self._active = False

	async def close(self) -> None:
		if self._session is None:
			return
		await self._session.close()
		self._session = None
		self._active = False

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


class SQLAlchemyDBTransactionFactory(DBTransactionFactory):
	"""Factory for creating SQLAlchemy transaction adapters."""

	def __init__(self, connection: DatabaseConnection) -> None:
		self._connection = connection

	def create(self) -> DBTransaction:
		return SQLAlchemyDBTransaction(connection=self._connection)

