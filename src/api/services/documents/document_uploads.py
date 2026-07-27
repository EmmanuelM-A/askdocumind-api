"""
Service module for handling document uploads.
"""

import asyncio
import uuid
from typing import List
from uuid import UUID

from fastapi import UploadFile

from src.api.services.validation.document import UploadDocumentsRequest
from src.api.services.validation.helper import check_if_chat_exists
from src.components.ingestion.document_processor import DocumentProcessor
from src.config.configs import settings
from src.config.constants import ProcessingStatus
from src.database.models import Document
from src.database.repository.interfaces import (
    ChatSessionRepositoryInterface,
    DocumentRepositoryInterface,
    DocumentSearchCriteria,
    DBTransactionFactory,
)

from src.errors.custom_exceptions import (
    conflict_error,
    database_error,
    unprocessable_entity_error,
    not_found_error,
)
from src.logger.base_logger import BaseLogger

_MAX_FILE_SIZE_BYTES = settings.files.MAX_FILE_SIZE_MB * 1024 * 1024
_MAX_FILES_PER_CHAT_BYTES = settings.files.MAX_FILES_PER_CHAT_MB * 1024 * 1024


class UploadDocumentService:
    """Service class for handling document uploads."""

    def __init__(
        self,
        document_processor: DocumentProcessor,
        chat_session_repo: ChatSessionRepositoryInterface,
        document_repo: DocumentRepositoryInterface,
        tx_factory: DBTransactionFactory,
    ) -> None:
        self._document_processor = document_processor
        self._chat_session_repo = chat_session_repo
        self._document_repo = document_repo
        self._tx_factory = tx_factory
        self._logger = BaseLogger(__name__)

    async def handle_document_uploads(
        self, owner_id: UUID, request: UploadDocumentsRequest
    ) -> int:
        """
        Handle the document upload process, including validation, storage, and vector processing.
        Returns the number of successfully uploaded documents.
        """
        await check_if_chat_exists(
            chat_id=request.chat_id,
            owner_id=owner_id,
            chat_session_repo=self._chat_session_repo,
        )

        self._logger.debug(f"Chat {request.chat_id} validated for user {owner_id}")

        await self._assert_no_duplicate_uploads(request)
        await self._assert_document_count_limit(request.chat_id, len(request.documents))

        failed_to_upload: List[str] = []
        docs_saved: int = 0

        for uploaded_file in request.documents:
            filename = self._clean_filename(uploaded_file.filename or "Unnamed file")
            self._logger.debug(f"Processing uploaded file '{filename}'")

            document_data = await self._read_data_from_upload(uploaded_file)

            incoming_bytes = len(document_data)
            exceeds = await self._do_incoming_bytes_exceed_chat_limit(
                chat_session_id=request.chat_id,
                incoming_bytes=incoming_bytes,
            )

            if exceeds:
                failed_to_upload.append(filename)
                continue

            document = Document(
                id=uuid.uuid4(),
                session_id=request.chat_id,
                source=filename,
                source_size=len(document_data),
                processing_status=ProcessingStatus.COMPLETED,
            )

            async with self._tx_factory.create() as tx:
                doc_id = await self._document_repo.create(
                    data=document,
                    tx=tx,
                )

                docling_document = self._document_processor.extract(
                    document_data=document_data,
                    filename=filename,
                )
                chunks = self._document_processor.chunk(docling_document)

                await self._document_processor.save_document_chunks(
                    chunks=chunks,
                    chat_session_id=request.chat_id,
                    document_id=doc_id,
                    tx=tx,
                )
                docs_saved += 1

        self._logger.debug(
            f"Successfully uploaded {docs_saved}/{len(request.documents)} " +
            f"documents for chat {request.chat_id}"
        )

        return docs_saved

    async def fetch_uploaded_document_metadata(
        self, chat_id: UUID, owner_id: UUID
    ) -> List[dict]:
        """Fetch metadata for uploaded documents associated with a chat session."""
        await check_if_chat_exists(
            chat_id=chat_id,
            owner_id=owner_id,
            chat_session_repo=self._chat_session_repo,
        )

        documents = await self._document_repo.list_by(
            criteria=DocumentSearchCriteria(session_id=chat_id)
        )

        return [document.to_dict() for document in documents]

    async def delete_uploaded_document(
        self, chat_id: UUID, owner_id: UUID, document_id: UUID
    ) -> None:
        """Delete an uploaded document after verifying chat ownership."""
        await check_if_chat_exists(
            chat_id=chat_id,
            owner_id=owner_id,
            chat_session_repo=self._chat_session_repo,
        )

        document = await self._document_repo.get_by_criteria(
            criteria=DocumentSearchCriteria(
                id=document_id,
                session_id=chat_id,
            )
        )

        if document is None:
            raise not_found_error(
                message=(
                    f"Document with ID {document_id} "
                    f"was not found for chat {chat_id}."
                ),
                error_code="DOCUMENT_NOT_FOUND",
            )

        await self._document_repo.delete(document_id)

        self._logger.info(f"Document {document_id} deleted from chat {chat_id}.")

    # ========================== HELPER METHODS ==========================

    async def _assert_document_count_limit(
        self, chat_session_id: UUID, incoming_count: int
    ) -> None:
        existing = await self._document_repo.list_by(
            criteria=DocumentSearchCriteria(session_id=chat_session_id)
        )
        limit = settings.files.MAX_DOCUMENTS_PER_CHAT
        if len(existing) + incoming_count > limit:
            raise conflict_error(
                message=(
                    f"Uploading these files would exceed the maximum of "
                    f"{limit} documents allowed per chat session."
                ),
                error_code="MAX_DOCUMENTS_PER_CHAT_EXCEEDED",
            )

    @staticmethod
    def _normalize_filename(filename: str) -> str:
        return filename.strip().lower()

    @staticmethod
    def _clean_filename(filename: str) -> str:
        return filename.strip()

    async def _assert_no_duplicate_uploads(
        self, request: UploadDocumentsRequest
    ) -> None:
        incoming_by_normalized: dict[str, str] = {}
        duplicates_in_request: set[str] = set()

        for upload in request.documents:
            filename = upload.filename or ""
            normalized = self._normalize_filename(filename)
            if normalized in incoming_by_normalized:
                duplicates_in_request.add(filename)
                duplicates_in_request.add(incoming_by_normalized[normalized])
            else:
                incoming_by_normalized[normalized] = filename

        if duplicates_in_request:
            duplicate_list = ", ".join(sorted(duplicates_in_request))
            raise conflict_error(
                message=f"Duplicate document names in request: {duplicate_list}.",
                error_code="DUPLICATE_DOCUMENTS_IN_REQUEST",
            )

        existing_documents = await self._document_repo.list_by(
            criteria=DocumentSearchCriteria(session_id=request.chat_id)
        )
        existing_names = {
            self._normalize_filename(document.source)  # type: ignore
            for document in existing_documents
            if document.source  # type: ignore
        }

        duplicates_in_chat = sorted(
            original_name
            for normalized, original_name in incoming_by_normalized.items()
            if normalized in existing_names
        )

        if duplicates_in_chat:
            duplicate_list = ", ".join(duplicates_in_chat)
            raise conflict_error(
                message=(
                    "One or more documents already exist for this chat: "
                    f"{duplicate_list}."
                ),
                error_code="DOCUMENT_ALREADY_EXISTS",
            )

    async def _read_data_from_upload(self, upload: UploadFile) -> bytes:
        try:
            data = await asyncio.to_thread(upload.file.read)
        except (FileNotFoundError, IOError) as e:
            raise database_error(
                message=f"Failed to process uploaded file {upload.filename}",
                error_code="DOCUMENT_READ_FAILED",
                stack_trace=str(e),
            )

        if len(data) > _MAX_FILE_SIZE_BYTES:
            raise unprocessable_entity_error(
                message=(
                    f"File '{upload.filename}' exceeds the maximum size of "
                    f"{_MAX_FILE_SIZE_BYTES:.1f} MB."
                ),
                error_code="FILE_SIZE_LIMIT_EXCEEDED",
            )

        return data

    async def _do_incoming_bytes_exceed_chat_limit(
        self, chat_session_id: UUID, incoming_bytes: int
    ) -> bool:
        current_mb_in_chat = await self._document_repo.get_total_size_mb(
            chat_session_id=chat_session_id
        )
        current_bytes_in_chat = int(current_mb_in_chat * 1024 * 1024)
        return current_bytes_in_chat + incoming_bytes > _MAX_FILES_PER_CHAT_BYTES
