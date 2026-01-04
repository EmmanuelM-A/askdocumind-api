"""
Responsible for defining all the database models used in the application.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    String,
    UUID,
    Text,
    Integer,
    BigInteger,
    Enum,
    ForeignKey,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from src.config.constants import ChatMessageRole, ProcessingStatus

Base = declarative_base()
metadata = Base.metadata


class ChatSession(Base):
    """Model representing a chat session."""

    __tablename__ = "chat_session"

    # Columns
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(Text, nullable=True)
    total_messages = Column(Integer, default=0, nullable=False)
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

    def __repr__(self):
        return f"Title: {self.title} | Total messages: {self.total_messages}"


class Document(Base):
    """Model representing an uploaded document."""

    __tablename__ = "document"

    # Columns
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    vector_id = Column(String(255), nullable=True)
    processing_status = Column(
        Enum(ProcessingStatus), default=ProcessingStatus.PENDING, nullable=False
    )
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship
    session = relationship("ChatSession", back_populates="documents")


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
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationship
    session = relationship("ChatSession", back_populates="messages")
