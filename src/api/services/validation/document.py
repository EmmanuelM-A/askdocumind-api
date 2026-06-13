from typing import List, Optional
from uuid import UUID
from zipfile import Path

from fastapi import UploadFile
from pydantic import BaseModel, Field, field_validator
from src.config.configs import settings


class UploadDocumentsRequest(BaseModel):
    """
    Request model for document uploads.
    """

    documents: List[UploadFile] = Field(
        ...,
        description="List of file documents to be uploaded",
        min_length=1,
        max_length=5,
    )
    chat_id: UUID = Field(..., description="The chat session identifier")

    @field_validator("documents", mode="before")
    @classmethod
    def validate_file_extensions(cls, files: List[UploadFile]) -> List[UploadFile]:
        allowed = {ext.lstrip(".") for ext in settings.files.ALLOWED_FILE_EXTENSIONS}
        invalid = [
            f.filename
            for f in files
            if Path(f.filename or "").suffix.lower().lstrip(".") not in allowed
        ]
        if invalid:
            raise ValueError(
                f"Unsupported file type(s): {', '.join(invalid)}. " # type: ignore
                f"Allowed: {', '.join(sorted(allowed))}"
            )
        return files


class FetchUploadedDocumentsRequest(BaseModel):
    """
    Request model for fetching uploaded documents.
    """

    document_ids: Optional[List[UUID]] = Field(
        None,
        description="Optional list of document IDs to retrieve. "
        "If not provided, all documents will be fetched.",
        min_length=1,
    )
    chat_id: UUID = Field(..., description="The chat session identifier")


class FetchDocumentMetadataRequest(BaseModel):
    """
    Request model for fetching document metadata.
    """

    chat_id: UUID = Field(..., description="The chat session identifier")
    owner_id: UUID = Field(
        ..., description="The user identifier of the chat session owner"
    )


class DeleteUploadedDocumentRequest(BaseModel):
    """Request model for deleting an uploaded document that belongs to a chat session."""

    chat_id: UUID = Field(..., description="The chat session identifier")
    owner_id: UUID = Field(
        ..., description="The user identifier of the chat session owner"
    )
    document_id: UUID = Field(..., description="The document identifier")
