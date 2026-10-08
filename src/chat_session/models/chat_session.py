import uuid
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Text, UUID, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.chat_session.models.chat_message import ChatMessage
from src.chat_session.models.mapper import ViewableChatSession
from src.database import Base
from src.uploads import Document


class ChatSession(Base):
    """Model representing a chat session."""

    __tablename__ = "chat_sessions"
    __mapper_args__ = {"eager_defaults": True}

    # Columns
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def viewable(self) -> ViewableChatSession:
        """
        Return a viewable representation of the ChatSession.
        """
        return ViewableChatSession(
            id=self.id,
            title=self.title,
            created_at=self.created_at.isoformat(),
        )
