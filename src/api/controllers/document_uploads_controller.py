"""
Controller layer responsible for handling document uploads.
"""

from typing import Optional
from uuid import UUID

from fastapi import Request, status
from starlette.responses import JSONResponse

from src.api.services.documents.document_uploads import UploadDocumentService
from src.api.services.service_factory import get_upload_service
from src.api.services.validation.document import UploadDocumentsRequest
from src.api.utils.api_responses import SuccessResponseModel
from src.api.utils.response_delivery import create_success_response


class DocumentUploadController:
    """
    Orchestrates document upload requests between API and service layers.
    """

    def __init__(self):
        self._upload_service: Optional[UploadDocumentService] = None

    def lazy_init(self) -> None:
        if self._upload_service is None:
            self._upload_service = get_upload_service()

    async def upload_documents_endpoint(
        self, request: Request, input: UploadDocumentsRequest
    ) -> JSONResponse:
        self.lazy_init()
        assert self._upload_service is not None

        owner_id: UUID = request.state.anonymous_user_id
        quantity_uploaded = await self._upload_service.handle_document_uploads(
            owner_id=owner_id, request=input
        )

        response_model = SuccessResponseModel(
            message=f"Successfully uploaded {quantity_uploaded} document(s)."
        )
        return create_success_response(
            status_code=status.HTTP_201_CREATED, success_response_model=response_model
        )

    async def list_uploaded_documents_endpoint(
        self, request: Request, chat_id: UUID
    ) -> JSONResponse:
        self.lazy_init()
        assert self._upload_service is not None

        owner_id: UUID = request.state.anonymous_user_id
        documents = await self._upload_service.fetch_uploaded_document_metadata(
            chat_id=chat_id, owner_id=owner_id
        )

        response_model = SuccessResponseModel(
            message=f"Successfully fetched {len(documents)} document(s).",
            data={"documents": documents},
        )
        return create_success_response(
            status_code=status.HTTP_200_OK, success_response_model=response_model
        )

    async def delete_uploaded_document_endpoint(
        self, request: Request, document_id: UUID, chat_id: UUID
    ) -> JSONResponse:
        self.lazy_init()
        assert self._upload_service is not None

        owner_id: UUID = request.state.anonymous_user_id
        await self._upload_service.delete_uploaded_document(
            chat_id=chat_id, owner_id=owner_id, document_id=document_id
        )

        response_model = SuccessResponseModel(
            message="Successfully deleted the document."
        )
        return create_success_response(
            status_code=status.HTTP_200_OK,
            success_response_model=response_model,
        )
