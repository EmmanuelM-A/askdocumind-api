"""
Routes for the document upload endpoints.
"""

from uuid import UUID

from fastapi import APIRouter, Request, UploadFile, File, Form

from src.api.controllers.document_uploads_controller import DocumentUploadController
from src.api.services.validation.document import UploadDocumentsRequest

documents_router = APIRouter(prefix="/documents", tags=["Documents"])

_controller = DocumentUploadController()


@documents_router.get("/", summary="List uploaded documents")
async def list_uploaded_documents(request: Request, chat_id: UUID):
    """Get all uploaded document metadata for a chat session."""
    return await _controller.list_uploaded_documents_endpoint(request, chat_id)


@documents_router.post(
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
                                "description": "Multiple document files to upload (1-10 files, max 10MB each)",
                            },
                            "chat_id": {
                                "type": "string",
                                "format": "uuid",
                                "description": "The chat session identifier",
                            },
                        },
                        "required": ["documents", "chat_id"],
                    }
                }
            }
        }
    },
)
async def upload_documents(
    request: Request,
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
    upload_request = UploadDocumentsRequest(documents=documents, chat_id=chat_id)
    return await _controller.upload_documents_endpoint(request, upload_request)


@documents_router.delete("/{document_id}", summary="Delete uploaded document")
async def delete_uploaded_document(request: Request, document_id: UUID, chat_id: UUID):
    """Delete an uploaded document by ID within a chat session."""
    return await _controller.delete_uploaded_document_endpoint(request, document_id, chat_id)
