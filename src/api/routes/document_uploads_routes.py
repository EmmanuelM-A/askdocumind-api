"""
Routes for the document upload endpoints.
Provides API routes for interacting with the Chat Session.
"""

from fastapi import APIRouter

from src.api.controllers.document_uploads_controller import DocumentUploadController

document_upload_router = APIRouter(prefix="/uploads", tags=["Chat Session"])

_controller = DocumentUploadController()


@document_upload_router.get("/", summary="Get all document uploads")
async def get_document_uploads():
    pass


@document_upload_router.post("/", summary="Upload documents")
async def upload_documents():
    pass
