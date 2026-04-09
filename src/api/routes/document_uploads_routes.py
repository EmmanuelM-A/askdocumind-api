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


@document_upload_router.post(
    "/", 
    summary="Upload documents",
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "documents": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                                "description": "Multiple document files to upload (1-10 files, max 10MB each)"
                            },
                            "chat_id": {
                                "type": "string",
                                "format": "uuid",
                                "description": "The chat session identifier"
                            }
                        },
                        "required": ["documents", "chat_id"]
                    }
                }
            }
        }
    }
)
async def upload_documents(
    documents: list[UploadFile] = File(
        ..., description="List of document files to upload (PDF, DOCX, TXT, MD)"
    ),
    chat_id: UUID = Form(..., description="The target chat session ID"),
):
    """
    Upload multiple documents to a chat session.

    **Document Status Flow:**
    - **PROCESSING**: Initial status when documents are uploaded and ingestion begins
    - **COMPLETED**: Documents successfully indexed and vectors stored
    - **FAILED**: Error occurred during processing or vector storage

    **Parameters:**
    - **documents**: List of files to upload (1-10 files, max 10MB each)
    - **chat_id**: UUID of the target chat session
    - **Allowed formats**: .pdf, .docx, .txt, .md
    """
    request = UploadDocumentsRequest(documents=documents, chat_id=chat_id)
    return await _controller.upload_files_endpoint(request)


# @document_upload_router.post("/metadata", summary="Fetch document metadata")
# async def fetch_uploaded_document(request: FetchUploadedDocumentsRequest):
#     """Fetch metadata for specific document IDs for a given chat."""
#     return await _controller.fetch_document_endpoint(request)
