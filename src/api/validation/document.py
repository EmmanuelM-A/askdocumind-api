from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from pydantic import BaseModel, Field, field_validator

from src.config.configs import settings
from src.errors.custom_exceptions import unprocessable_entity_error


class UploadDocumentsRequest(BaseModel):
    """
    Request model for document uploads.
    """

    documents: list[UploadFile] = Field(
        ...,
        description="List of file documents to be uploaded",
        min_length=1,
        max_length=5,
    )
    chat_id: UUID = Field(..., description="The chat session identifier")

    @field_validator("documents", mode="before")
    @classmethod
    def validate_file_extensions(cls, files: list[UploadFile]) -> list[UploadFile]:
        double_ext = [
            f.filename for f in files if len(Path(f.filename or "").suffixes) > 1
        ]
        if double_ext:
            raise unprocessable_entity_error(
                message="Files with multiple extensions are not allowed",
                error_code="INVALID_FILE_EXTENSION",
            )

        unsupported = [
            f.filename
            for f in files
            if Path(f.filename or "").suffix.lower() not in settings.files.ALLOED_FILE_EXTENSIONS
        ]
        if unsupported:
            allowed = ", ".join(sorted(settings.files.ALLOED_FILE_EXTENSIONS))
            raise unprocessable_entity_error(
                message=(
                    f"Unsupported file type(s): {', '.join(unsupported)}. "
                    f"Allowed extensions are: {allowed}."
                ),
                error_code="UNSUPPORTED_FILE_TYPE",
            )

        return files


class FetchUploadedDocumentsRequest(BaseModel):
    """
    Request model for fetching uploaded documents by ID.
    """

    document_ids: list[UUID] | None = Field(
        None,
        description="Optional list of document IDs to retrieve. "
        "If not provided, all documents will be fetched.",
        min_length=1,
    )
    chat_id: UUID = Field(..., description="The chat session identifier")
