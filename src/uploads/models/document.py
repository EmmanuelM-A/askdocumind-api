from datetime import datetime

from sqlalchemy import func, DateTime
from sqlalchemy.orm import Mapped, mapped_column


class Document(Base):
    """Model representing an uploaded document's metadata."""

    __tablename__ = "document"
    __table_args__ = (
        UniqueConstraint("session_id", "source", name="uq_document_session_source"),
    )

    # Columns
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    source = Column(String(255), nullable=False)
    source_size = Column(BigInteger, nullable=False)
    source_type = Column(
        Enum(DocumentSourceType), default=DocumentSourceType.UPLOAD, nullable=False
    )
    processing_status = Column(
        Enum(ProcessingStatus), default=ProcessingStatus.PROCESSING, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    session = relationship("ChatSession", back_populates="documents")
    chunks = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"Document(source={self.source}, size={self.source_size})"

    def __str__(self) -> str:
        return str(self.source) if self.source is not None else "Unknown Document"

    def to_dict(self) -> dict:
        """Return JSON-serializable dict representation of the Document."""
        return {
            "id": _serialize_value(self.id),
            "session_id": _serialize_value(self.session_id),
            "source": self.source,
            "source_size": self.source_size,
            "source_type": _serialize_value(self.source_type),
            "processing_status": _serialize_value(self.processing_status),
            "created_at": _serialize_value(self.created_at),
            "updated_at": _serialize_value(self.updated_at),
        }

    def to_json(self) -> str:
        """Return a JSON string representation of the Document."""
        return json.dumps(self.to_dict(), indent=4)
