"""
Controller layer responsible for handling document uploads.
Handles application logic related to document uploads and interactions with the
service layer.
"""

from typing import Optional

from fastapi import status
from starlette.responses import JSONResponse

from src.api.services.documents.document_uploads import UploadDocumentService
from src.api.services.service_factory import get_upload_service
from src.api.services.validation.document import (
    DeleteUploadedDocumentRequest,
    FetchDocumentMetadataRequest,
    UploadDocumentsRequest,
)
from src.api.utils.api_responses import SuccessResponseModel
from src.api.utils.response_delivery import create_success_response


class DocumentUploadController:
    """
    Orchestrates document upload requests between API and service layers.
    """

    def __init__(self):
        self._upload_service: Optional[UploadDocumentService] = None

    def lazy_init(self) -> None:
        """Lazy initialize variables."""
        if self._upload_service is None:
            self._upload_service = get_upload_service()

    async def upload_documents_endpoint(
        self, input: UploadDocumentsRequest
    ) -> JSONResponse:
        """
        Receive files and chat_id from FastAPI route, call service and return response.
        """
        self.lazy_init()
        assert self._upload_service is not None

        quantity_uploaded = await self._upload_service.handle_document_uploads(input)

        response_model = SuccessResponseModel(
            message=f"Successfully uploaded {quantity_uploaded} document(s)."
        )

        return create_success_response(
            status_code=status.HTTP_201_CREATED, success_response_model=response_model
        )

    async def list_uploaded_documents_endpoint(
        self, input: FetchDocumentMetadataRequest
    ) -> JSONResponse:
        """
        Fetch the metadata for uploaded documents.
        """
        self.lazy_init()
        assert self._upload_service is not None

        documents = await self._upload_service.fetch_uploaded_document_metadata(input)

        response_model = SuccessResponseModel(
            message=f"Successfully fetched {len(documents)} document(s).",
            data={"documents": documents},
        )

        return create_success_response(
            status_code=status.HTTP_200_OK, success_response_model=response_model
        )

    async def delete_uploaded_document_endpoint(
        self, input: DeleteUploadedDocumentRequest
    ) -> JSONResponse:
        """
        Delete uploaded document metadata and storage file for a chat.
        """
        self.lazy_init()
        assert self._upload_service is not None

        await self._upload_service.delete_uploaded_document(input)

        response_model = SuccessResponseModel(
            message="Successfully deleted the document."
        )

        return create_success_response(
            status_code=status.HTTP_200_OK,
            success_response_model=response_model,
        )
