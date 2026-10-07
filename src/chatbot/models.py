"""
Responsible for defining all the database models used in the application.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    UUID,
    BigInteger,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import declarative_base, relationship

from src.config.constants import ChatMessageRole, DocumentSourceType, ProcessingStatus
from src.logger.base_logger import BaseLogger
from src.utils import format_datetime

_logger = BaseLogger(__name__)

Base = declarative_base()
metadata = Base.metadata


def _serialize_value(value: Any) -> Any:
    """Serialize common types to JSON-friendly representations."""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return format_datetime(value)
    # Enum values (SQLAlchemy Enum wrapper) -> get name if available
    try:
        # Many enums are instances of Python Enum and expose .name
        return value.name
    except Exception as e:  # noqa: BLE001
        _logger.debug(f"Could not serialize enum-like value {value!r}: {e}")
    return value


class ChatSession(Base):
    """Model representing a chat session."""

    __tablename__ = "chat_session"

    # Columns
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    messages = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan"
    )
    documents = relationship(
        "Document", back_populates="session", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return str(self.title) if self.title is not None else "Unknown Chat Session"

    def __repr__(self):
        return f"Title: {self.title}"

    def to_dict(self) -> dict:
        """Return JSON-serializable dict representation of the ChatSession.

        Note: related collections (`messages`, `documents`) are not expanded here
        to avoid loading potentially large relationships. If you want to include
        related objects, fetch them explicitly and call their `to_dict`.
        """
        return {
            "id": _serialize_value(self.id),
            "title": self.title,
            "created_at": _serialize_value(self.created_at),
        }

    def to_json(self) -> str:
        """Return a JSON string representation of the ChatSession."""
        return json.dumps(self.to_dict(), indent=4)


class ChatMessage(Base):
    """Model representing a chat message."""

    __tablename__ = "chat_message"

    # Columns
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(Enum(ChatMessageRole), nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(ARRAY(String), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationship
    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self):
        return f"ChatMessage(role={self.role}, size={self.content})"

    def __str__(self) -> str:
        return str(self.content) if self.content is not None else "Unknown Message"

    def to_dict(self) -> dict:
        """Return JSON-serializable dict representation of the ChatMessage."""
        return {
            "id": _serialize_value(self.id),
            "session_id": _serialize_value(self.session_id),
            "role": _serialize_value(self.role),
            "content": self.content,
            "sources": self.sources,
            "created_at": _serialize_value(self.created_at),
        }

    def to_json(self) -> str:
        """Return a JSON string representation of the ChatMessage."""
        return json.dumps(self.to_dict(), indent=4)
