from pydantic import BaseModel, Field


class CreateChatSessionData(BaseModel):
    """The data needed to create or initialize a chat session."""

    title: str = Field(..., description="The title of the chat session")
