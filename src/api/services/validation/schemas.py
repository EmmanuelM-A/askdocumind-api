"""
Contains (pydantic) validation schemas used to validated inputted data for
operations, requests and responses.
"""

from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel


class CreateChatSchema(BaseModel):
    """The data needed to create a new chat."""

    title: str


class UpdateChatMetadataSchema(BaseModel):
    """The data needed to update chat metadata."""

    title: Optional[str] = None


class GetChatSchema(BaseModel):
    """The data needed to get a chat."""

    chat_id: UUID


class GetChatsSchema(BaseModel):
    """The data needed to get chats."""

    chat_ids: List[UUID]
