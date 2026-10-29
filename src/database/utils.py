"""
Database utility functions and classes for pagination and repository
management.
"""

from fastapi_pagination import Page, Params
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class Pagination(BaseModel):
    """Pagination parameters for database queries."""

    model_config = {"extra": "forbid"}

    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=100)

    @property
    def offset(self) -> int:
        """Calculate the offset for the current page."""
        return (self.page - 1) * self.limit


class BaseRepository:
    """Base class for repositories bound to one request-scoped session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _paginate(self, statement: Select, paginate: Pagination) -> Page:
        """Run a count query and a page query for an ordered SELECT."""
        count_statement = select(func.count()).select_from(
            statement.order_by(None).subquery()
        )
        total = (await self._session.execute(count_statement)).scalar_one()

        page_statement = statement.offset(paginate.offset).limit(paginate.limit)
        items = (await self._session.execute(page_statement)).scalars().all()

        params = Params(page=paginate.page, size=paginate.limit)
        return Page.create(list(items), params, total=total)
