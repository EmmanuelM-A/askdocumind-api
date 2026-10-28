from uuid import UUID

from fastapi import UploadFile
from pydantic import Field

from src.config.configs import settings
from src.shared.utils import CamelCaseSerializer


class DeleteUploadedFilesRequest(CamelCaseSerializer):
    file_ids: list[UUID] = Field(
        min_length=1, max_length=settings.uploads.MAX_DOCS_PER_SESSION
    )
