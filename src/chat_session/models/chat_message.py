import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.chat_session.models.chat_session import ChatSession
from src.chat_session.domain.chat import ChatMessageRole
from src.chat_session.models.mapper import ViewableChatMessage
from src.database import Base


class ChatMessage(Base):
    """Model representing a chat message."""

    __tablename__ = "chat_messages"
    __mapper_args__ = {"eager_defaults": True}

    # Columns
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[ChatMessageRole] = mapped_column(Enum(ChatMessageRole))
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list[str]] = mapped_column(ARRAY(String))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    session: Mapped["ChatSession"] = relationship(back_populates="messages")

    def to_dict(self) -> ViewableChatMessage:
        """
        Return a viewable representation of the ChatMessage.
        """
        return ViewableChatMessage(
            id=self.id,
            chat_session_id=self.chat_session_id,
            role=self.role.value,
            content=self.content,
            sources=self.sources,
            created_at=self.created_at.isoformat(),
        )
