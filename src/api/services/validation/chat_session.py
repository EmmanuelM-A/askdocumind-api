from uuid import UUID

from pydantic import BaseModel, Field


class CreateChatSessionSchema(BaseModel):
    """The data needed to create a new chat session."""

    title: str = Field(..., description="The title of the chat session")
    owner_id: UUID = Field(
        ..., description="The user identifier of the chat session owner"
    )


class GetChatSessionSchema(BaseModel):
    """The data needed to fetch a chat session."""

    chat_id: UUID = Field(..., description="The chat session identifier")
    owner_id: UUID = Field(
        ..., description="The user identifier of the chat session owner"
    )


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

