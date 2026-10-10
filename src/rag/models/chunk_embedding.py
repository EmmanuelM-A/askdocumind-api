"""
Contains the SQLAlchemy model for document chunk embeddings.
"""

import uuid
from datetime import datetime
from pgvector.sqlalchemy import Vector

from sqlalchemy import UUID, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database.orm_base import Base
from src.rag.models.mapper import ViewableChunkEmbedding


class ChunkEmbedding(Base):
    """Model representing a chunk embedding for a resource"""

    __tablename__ = "chunk_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=None,
    )

    def viewable(self) -> ViewableChunkEmbedding:
        """Return a viewable representation of the chunk embedding."""

        return ViewableChunkEmbedding(
            id=self.id,
            chat_session_id=self.chat_session_id,
            document_id=self.document_id,
            chunk_text=self.chunk_text,
            created_at=self.created_at.isoformat(),
            updated_at=self.updated_at.isoformat() if self.updated_at else None,
        )
