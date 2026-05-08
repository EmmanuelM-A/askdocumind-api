"""
Responsible for defining all the database models used in the application.
"""

import uuid
import json
from datetime import datetime
from typing import Any

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
    Sequence,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship, declarative_base
from pgvector.sqlalchemy import Vector

from src.config.constants import ChatMessageRole, ProcessingStatus
from src.utils import format_datetime

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
    except Exception:
        pass
    return value


class User(Base):
    """Model representing a minimalistic user."""

    __tablename__ = "user"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(),
        index=True,
    )
    last_seen_at = Column(DateTime, index=True)

    def __repr__(self):
        return f"User(id={self.id}, created_at={self.created_at})"

    def __str__(self) -> str:
        return str(self.id) if self.id is not None else "Unknown User"

    def to_dict(self) -> dict:
        """Return JSON-serializable dict representation of the User."""
        return {
            "id": _serialize_value(self.id),
            "created_at": _serialize_value(self.created_at),
            "last_seen_at": _serialize_value(self.last_seen_at),
        }

    def to_json(self) -> str:
        """Return a JSON string representation of the User."""
        return json.dumps(self.to_dict(), indent=4)


class ChatSession(Base):
    """Model representing a chat session."""

    __tablename__ = "chat_session"

    # Columns
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(Text, nullable=True)
    total_messages = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now())

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
        return f"Title: {self.title} | Total messages: {self.total_messages}"

    def to_dict(self) -> dict:
        """Return JSON-serializable dict representation of the ChatSession.

        Note: related collections (`messages`, `documents`) are not expanded here
        to avoid loading potentially large relationships. If you want to include
        related objects, fetch them explicitly and call their `to_dict`.
        """
        return {
            "id": _serialize_value(self.id),
            "title": self.title,
            "total_messages": self.total_messages,
            "created_at": _serialize_value(self.created_at),
        }

    def to_json(self) -> str:
        """Return a JSON string representation of the ChatSession."""
        return json.dumps(self.to_dict(), indent=4)


class Document(Base):
    """Model representing an uploaded document's metadata."""

    __tablename__ = "document"
    __table_args__ = (
        UniqueConstraint("session_id", "filename", name="uq_document_session_filename"),
    )

    # Columns
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    vector_id = Column(UUID, nullable=True)
    processing_status = Column(
        Enum(ProcessingStatus), default=ProcessingStatus.PROCESSING, nullable=False
    )
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(),
        onupdate=lambda: datetime.now(),
    )

    # Relationship
    session = relationship("ChatSession", back_populates="documents")
    chunks = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"Document(filename={self.filename}, size={self.file_size})"

    def __str__(self) -> str:
        return str(self.filename) if self.filename is not None else "Unknown Document"

    def to_dict(self) -> dict:
        """Return JSON-serializable dict representation of the Document."""
        return {
            "id": _serialize_value(self.id),
            "session_id": _serialize_value(self.session_id),
            "filename": self.filename,
            "file_size": self.file_size,
            "vector_id": self.vector_id,
            "processing_status": _serialize_value(self.processing_status),
            "created_at": _serialize_value(self.created_at),
            "updated_at": _serialize_value(self.updated_at),
        }

    def to_json(self) -> str:
        """Return a JSON string representation of the Document."""
        return json.dumps(self.to_dict(), indent=4)


class DocumentChunk(Base):
    """Model representing a document vector chunk embedding"""

    __tablename__ = "document_chunk"

    # Columns
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("document.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index = Column(Integer, default=0, nullable=False)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now())

    # Relationship
    document = relationship("Document", back_populates="chunks")

    def __repr__(self) -> str:
        return (
            f"DocumentChunk(id={self.id}, document_id={self.document_id}, "
            f"chunk_index={self.chunk_index})"
        )

    def __str__(self) -> str:
        return f"Chunk {self.chunk_index} of document {self.document_id}"

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict representation of the chunk.

        Note: embeddings may be binary/array types; we attempt to convert
        them to a list when possible, otherwise they are represented as
        None to avoid serialization errors.
        """
        def _serialize_embedding(val: object) -> object:
            if val is None:
                return None
            try:
                # numpy arrays and similar expose tolist()
                if hasattr(val, "tolist"):
                    return val.tolist()
                # sequences (lists/tuples)
                if isinstance(val, (list, tuple)):
                    return list(val)
            except Exception:
                pass
            return None

        return {
            "id": _serialize_value(self.id),
            "document_id": _serialize_value(self.document_id),
            "chunk_index": self.chunk_index,
            "chunk_text": self.chunk_text,
            "embedding": _serialize_embedding(self.embedding),
            "created_at": _serialize_value(self.created_at),
        }

    def to_json(self) -> str:
        """Return a JSON string representation of the chunk."""
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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now())

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
            "created_at": _serialize_value(self.created_at),
        }

    def to_json(self) -> str:
        """Return a JSON string representation of the ChatMessage."""
        return json.dumps(self.to_dict(), indent=4)
