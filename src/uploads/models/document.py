import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.chat_session import ChatSession
from src.database import Base
from src.uploads.domain.document import ProcessingStatus
from src.uploads.models.mapper import ViewableDocument


class Document(Base):
    """Model representing an uploaded document's metadata."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "chat_session_id", "filename", name="uq_document_chat_session_filename"
        ),
    )
    __mapper_args__ = {"eager_defaults": True}

    # Columns
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
    )
    filename: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(BigInteger)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus), default=ProcessingStatus.PROCESSING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    session: Mapped["ChatSession"] = relationship(back_populates="documents")

    def to_dict(self) -> ViewableDocument:

        return ViewableDocument(
            id=self.id,
            chat_session_id=self.chat_session_id,
            filename=self.filename,
            file_size=self.file_size,
            processing_status=self.processing_status,
            created_at=self.created_at.isoformat(),
            updated_at=self.updated_at.isoformat(),
        )
