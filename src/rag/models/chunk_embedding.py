import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.configs import settings
from src.database.orm_base import Base
from src.rag.models.mapper import ViewableChunkEmbedding

_EMBEDDING_DIMENSIONS = settings.rag.EMBEDDING_DIMENSIONS


if TYPE_CHECKING:
    from src.uploads.models.document import Document


class ChunkEmbedding(Base):
    """Model representing one embedded chunk of a document."""

    __tablename__ = "chunk_embeddings"

    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "chat_session_id"],
            ["documents.id", "documents.chat_session_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_chunk_document_index",
        ),
        Index("ix_chunk_embeddings_chat_session_id", "chat_session_id"),
        Index(
            "ix_chunk_embeddings_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(_EMBEDDING_DIMENSIONS), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        back_populates="chunk_embeddings",
    )

    def viewable(self) -> ViewableChunkEmbedding:
        """Return a viewable representation of the chunk embedding."""

        return ViewableChunkEmbedding(
            id=self.id,
            document_id=self.document_id,
            chat_session_id=self.chat_session_id,
            chunk_index=self.chunk_index,
            chunk_text=self.chunk_text,
            created_at=self.created_at.isoformat(),
        )
