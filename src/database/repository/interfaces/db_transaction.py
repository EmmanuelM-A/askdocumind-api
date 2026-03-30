"""
ORM-agnostic transaction contracts for repository operations.

Concrete adapters (for example, SQLAlchemy) should implement this interface
and encapsulate backend-specific session/transaction behavior.
"""

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Any, Optional, Type


class DBTransaction(ABC):
	"""Represents a single database transaction boundary."""

	@property
	@abstractmethod
	def is_active(self) -> bool:
		"""Return whether the transaction is currently active."""
		raise NotImplementedError

	@abstractmethod
	async def add(self, entity: Any) -> None:
		"""Stage an entity for insert/update within the transaction."""
		raise NotImplementedError

	@abstractmethod
	async def add_all(self, entities: list[Any]) -> None:
		"""Stage multiple entities for insert/update within the transaction."""
		raise NotImplementedError

	@abstractmethod
	async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
		"""Execute a backend query/statement within the transaction."""
		raise NotImplementedError

	@abstractmethod
	async def flush(self) -> None:
		"""Flush pending operations without committing the transaction."""
		raise NotImplementedError

	@abstractmethod
	async def commit(self) -> None:
		"""Commit the transaction."""
		raise NotImplementedError

	@abstractmethod
	async def rollback(self) -> None:
		"""Rollback all uncommitted changes in the transaction."""
		raise NotImplementedError

	@abstractmethod
	async def close(self) -> None:
		"""Release underlying resources held by the transaction."""
		raise NotImplementedError

	@abstractmethod
	async def __aenter__(self) -> "DBTransaction":
		"""Enter a transaction context manager."""
		raise NotImplementedError

	@abstractmethod
	async def __aexit__(
		self,
		exc_type: Optional[Type[BaseException]],
		exc: Optional[BaseException],
		tb: Optional[TracebackType],
	) -> None:
		"""Commit on success or rollback on failure, then close resources."""
		raise NotImplementedError


class DBTransactionFactory(ABC):
	"""Factory contract that starts new database transactions."""

	@abstractmethod
	def create(self) -> DBTransaction:
		"""Create a new transaction object."""
		raise NotImplementedError

