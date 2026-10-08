from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """
    Base repository class that provides common database operations.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def _execute_statement(self, statement) -> Any:
        """
        Execute a given SQLAlchemy statement within the current session.
        """
        async with self._session as session:
            return await session.execute(statement)


class Pagination(BaseModel):
    """Pagination parameters for database queries."""

    page: int = 1
    limit: int = 10

    @property
    def offset(self) -> int:
        """Calculate the offset for the current page."""
        return (self.page - 1) * self.limit
