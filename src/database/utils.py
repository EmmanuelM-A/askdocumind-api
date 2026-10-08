from pydantic import BaseModel


class Pagination(BaseModel):
    """Pagination parameters for database queries."""

    page: int = 1
    limit: int = 10

    @property
    def offset(self) -> int:
        """Calculate the offset for the current page."""
        return (self.page - 1) * self.limit
