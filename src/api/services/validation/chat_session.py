from uuid import UUID

from pydantic import BaseModel, Field


class DeleteChatSessionSchema(BaseModel):
    """The data needed to delete a chat session."""

    chat_id: UUID = Field(..., description="The chat session identifier")
    owner_id: UUID = Field(
        ..., description="The user identifier of the chat session owner"
    )


class InitializeChatSessionSchema(BaseModel):
    """The data needed to initialize a chat session."""

    user_id: UUID = Field(
        ..., description="The user identifier of the chat session owner"
    )
    title: str = Field(..., description="The title of the chat session")


class GetChatSessionMessagesSchema(BaseModel):
    """The data needed to fetch chat session messages."""

    chat_id: UUID = Field(..., description="The chat session identifier")
    owner_id: UUID = Field(
        ..., description="The user identifier of the chat session owner"
    )

