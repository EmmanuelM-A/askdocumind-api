"""
Defines the SQLAlchemy model for the User entity.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from src.auth.models.mapper import ViewableUser
from src.database import Base


class User(Base):
    """Model representing a minimalistic user."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def viewable(self) -> ViewableUser:
        """Return JSON-serializable dict representation of the User."""

        return ViewableUser(
            id=self.id,
            created_at=self.created_at.isoformat(),
            last_seen_at=self.last_seen_at.isoformat(),
        )
