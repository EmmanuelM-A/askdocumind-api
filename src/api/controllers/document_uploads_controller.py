"""
Controller layer responsible for handling document uploads.
Handles application logic related to document uploads and interactions with the
service layer.
"""

from typing import List
from uuid import UUID

from fastapi import UploadFile, status, File, Form
from starlette.responses import JSONResponse

from src.api.services.service_factory import get_upload_service
from src.api.services.validation.rag_validation import (
    FetchDocumentMetadataRequest,
)
from src.api.utils.response_delivery import create_success_response
from src.api.services.validation.rag_validation import UploadDocumentsRequest


class DocumentUploadController:
    """
    Orchestrates document upload requests between API and service layers.
    """

    def __init__(self):
        self.upload_service = None

    async def upload_files_endpoint(
        self, request: UploadDocumentsRequest
    ) -> JSONResponse:
        """Receive files and chat_id from FastAPI route, call service and return response."""

        if self.upload_service is None:
            self.upload_service = get_upload_service()

        response_model = await self.upload_service.handle_document_uploads(request)

        return create_success_response(
            status_code=status.HTTP_201_CREATED, success_response_model=response_model
        )

    async def list_uploaded_files_endpoint(
        self, request: FetchDocumentMetadataRequest
    ) -> JSONResponse:
        """Fetch the metadata for uploaded documents"""

        if self.upload_service is None:
            self.upload_service = get_upload_service()

        response_model = await self.upload_service.fetch_uploaded_document_metadata(
            request
        )
        return create_success_response(
            status_code=status.HTTP_200_OK, success_response_model=response_model
        )

    # async def fetch_document_endpoint(
    #     self, request: FetchDocumentMetadataRequest
    # ) -> JSONResponse:
    #     """Fetch document metadata via UploadService."""
    #     response_model = await self.upload_service.fetch_uploaded_document_metadata(
    #         request
    #     )
    #     return create_success_response(
    #         status_code=status.HTTP_200_OK, success_response_model=response_model
    #     )
