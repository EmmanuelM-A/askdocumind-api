"""
Service module for handling document uploads.
"""

from src.components.chatbot.chatbot_factory import get_chatbot
from src.database.models import ChatSession, Document
from src.database.repository.database_repository_factory import get_database_repository
from src.database.storage.storage_service import StorageService
from src.errors.custom_exceptions import throw_database_error
from src.services.validation.rag_validation import (
    UploadDocumentsRequest,
    check_if_chat_exists,
    FetchUploadedDocumentsRequest,
)


class UploadService:
    """Service class for handling document uploads."""

    def __init__(self, storage_service: StorageService) -> None:
        self.chat_session_repo = get_database_repository(ChatSession)
        self.document_repo = get_database_repository(Document)
        self.storage_service = storage_service
        self.chatbot = get_chatbot()

    async def handle_document_uploads(self, request: UploadDocumentsRequest):
        """Handles document upload requests."""

        # Check if chat session exists - raise error if not
        # Process and store uploaded documents
        # Return success response

        await check_if_chat_exists(
            chat_id=request.chat_id,
            chat_session_repo=self.chat_session_repo,
            chatbot=self.chatbot,
        )

        # Process and save document vectors
        self.chatbot.process_and_save_vectors(
            files=request.documents,
            index_id=str(request.chat_id),
        )

        # Store document data in storage (e.g., S3, local filesystem)
        for document in request.documents:
            key = f"{request.chat_id}/{document.filename}"
            data = document.file.read()
            try:
                self.storage_service.save(key, data)
            except IOError as e:
                throw_database_error(
                    message=f"Failed to store document {document.filename}",
                    error_code="DOCUMENT_STORAGE_FAILED",
                    stack_trace=str(e),
                )

        # Store document metadata in the database
        await self.document_repo.create_many(entities=[])

    def fetch_uploaded_documents(self, request: FetchUploadedDocumentsRequest):
        pass
