from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from src.components.chatbot.query_handler import validate_and_sanitize_query
from src.config.configs import settings
from src.logger.base_logger import BaseLogger

_logger = BaseLogger(__name__)


class ChatRequest(BaseModel):
    """
    Request model for chat interactions.
    """

    user_query: str = Field(
        ...,
        min_length=settings.app.MIN_QUERY_LENGTH,
        max_length=settings.app.MAX_QUERY_LENGTH,
        description="The user's chat query",
    )
    chat_id: UUID = Field(..., description="The chat session identifier")
    user_id: UUID = Field(
        ..., description="The user identifier of the chat session owner"
    )
    web_search_enabled: bool = Field(
        False, description="Flag to enable web search for the query"
    )

    @field_validator("user_query", mode="before")
    def validate_query(cls, value: str) -> str:
        """Ensure query is not just whitespace."""

        return validate_and_sanitize_query(query=value, logger=_logger)
