"""
Routes for the document upload endpoints.
Provides API routes for interacting with the Chat Session.
"""

from uuid import UUID

from fastapi import APIRouter, UploadFile, File, Form

from src.api.controllers.document_uploads_controller import DocumentUploadController
from src.api.services.validation.rag_validation import (
    FetchDocumentMetadataRequest,
    UploadDocumentsRequest,
)

document_upload_router = APIRouter(prefix="/uploads", tags=["Document Uploads"])

_controller = DocumentUploadController()


@document_upload_router.get("/", summary="Get the metadata of all uploaded documents")
async def get_document_uploads(chat_id: UUID):
    """Get all document uploads for a chat session (only metadata)."""
    request = FetchDocumentMetadataRequest(chat_id=chat_id)
    return await _controller.list_uploaded_files_endpoint(request)


@document_upload_router.post("/", summary="Upload documents")
async def upload_documents(
    documents: list[UploadFile] = File(...),
    chat_id: UUID = Form(...),
):
    """Upload files to a chat session."""
    request = UploadDocumentsRequest(documents=documents, chat_id=chat_id)
    return await _controller.upload_files_endpoint(request)


# @document_upload_router.post("/metadata", summary="Fetch document metadata")
# async def fetch_uploaded_document(request: FetchUploadedDocumentsRequest):
#     """Fetch metadata for specific document IDs for a given chat."""
#     return await _controller.fetch_document_endpoint(request)
