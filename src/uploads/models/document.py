import uuid
from datetime import datetime
from typing import TYPE_CHECKING

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

from src.database.orm_base import Base
from src.uploads.domain.document import DocumentStatus
from src.uploads.models.mapper import ViewableDocument

if TYPE_CHECKING:
    from src.chat_session.models.chat_session import ChatSession


class Document(Base):
    """Model representing an uploaded document's metadata."""

    __tablename__ = "documents"

    __table_args__ = (
        UniqueConstraint(
            "chat_session_id",
            "original_filename",
            name="uq_document_chat_session_filename",
        ),
    )

    # Columns
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(
        String(512),
        unique=True,
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(String(512), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    chat_session: Mapped["ChatSession"] = relationship(
        back_populates="documents",
    )

    def viewable(self) -> ViewableDocument:
        """Return a viewable representation of the document."""

        return ViewableDocument(
            id=self.id,
            chat_session_id=self.chat_session_id,
            filename=self.original_filename,
            content_type=self.content_type,
            size_bytes=self.size_bytes,
            checksum=self.checksum,
            status=self.status.value,
            error_message=self.error_message,
            created_at=self.created_at.isoformat(),
            updated_at=self.updated_at.isoformat(),
        )
