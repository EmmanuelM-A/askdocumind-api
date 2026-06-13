"""
Service module for handling document uploads.
"""

import asyncio
import uuid
from typing import List, Tuple, cast
from uuid import UUID

from fastapi import UploadFile

from src.api.services.validation.rag_validation import (
    UploadDocumentsRequest,
    check_if_chat_exists,
    FetchDocumentMetadataRequest,
    DeleteUploadedDocumentRequest,
)
from src.components.ingestion.vector_processor import VectorProcessor
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
        vector_processor: VectorProcessor,
        chat_session_repo: ChatSessionRepositoryInterface,
        document_repo: DocumentRepositoryInterface,
        tx_factory: DBTransactionFactory,
    ) -> None:
        self._vector_processor = vector_processor
        self._chat_session_repo = chat_session_repo
        self._document_repo = document_repo
        self._tx_factory = tx_factory

        self._logger = BaseLogger(__name__)

    async def handle_document_uploads(self, request: UploadDocumentsRequest) -> int:
        """
        Handle the document upload process, including validation, storage, and vector processing.
        Returns the number of successfully uploaded documents.
        """

        await check_if_chat_exists(
            chat_id=request.chat_id,
            owner_id=request.chat_id,
            chat_session_repo=self._chat_session_repo,
        )

        self._logger.debug(
            f"The chat {request.chat_id} has been validated successfully"
        )

        await self._assert_no_duplicate_uploads(request)

        entities: List[Document] = []
        documents: List[Tuple[UUID, str, bytes]] = []
        files_that_exceed_chat_limit: List[str] = []

        for uploaded_file in request.documents:
            filename = self._normalize_filename(
                uploaded_file.filename or "Unnamed file"
            )
            self._logger.debug(f"Processing uploaded file '{filename}'")

            data = await self._read_data_from_upload(uploaded_file)

            incoming_bytes = len(data)
            exceeds = await self._do_incoming_bytes_exceed_chat_limit(
                chat_session_id=request.chat_id,
                incoming_bytes=incoming_bytes,
            )

            if exceeds:
                files_that_exceed_chat_limit.append(filename)
                continue

            document = Document(
                id=uuid.uuid4(),
                session_id=request.chat_id,
                filename=filename,
                file_size=len(data),
                processing_status=ProcessingStatus.PROCESSING,
            )

            entities.append(document)
            documents.append((cast(UUID, document.id), filename, data))

        self._logger.debug(
            f"{len(documents)} document(s) entities created successfully"
        )
        self._logger.warning(
            f"{len(files_that_exceed_chat_limit)} files exceed chat limit"
        )

        if len(files_that_exceed_chat_limit) == len(request.documents):
            raise conflict_error(
                message=(
                    "All uploaded documents exceed the maximum total chat size limit of "
                    f"{_MAX_FILES_PER_CHAT_BYTES:.1f} MB."
                ),
                error_code="ALL_DOCUMENTS_EXCEED_CHAT_LIMIT",
            )

        async with self._tx_factory.create() as tx:
            created_entities = await self._document_repo.create_many(
                entities=entities,
                tx=tx,
            )

            self._logger.debug(
                f"Created {len(created_entities)} document entities successfully"
            )

            await self._vector_processor.process_and_save_vectors_from_uploads(
                chat_session_id=request.chat_id, documents=documents, tx=tx
            )

            await self._document_repo.bulk_update_processing_status(
                document_ids=created_entities,
                status=ProcessingStatus.COMPLETED,
                tx=tx,
            )

        return len(created_entities)

    async def fetch_uploaded_document_metadata(
        self, request: FetchDocumentMetadataRequest
    ) -> List[dict]:
        """
        Fetch metadata for uploaded documents associated with a chat session.
        """
        await check_if_chat_exists(
            chat_id=request.chat_id,
            owner_id=request.owner_id,
            chat_session_repo=self._chat_session_repo,
        )

        documents = await self._document_repo.list_by(
            criteria=DocumentSearchCriteria(session_id=request.chat_id)
        )

        return [document.to_dict() for document in documents]

    async def delete_uploaded_document(
        self, request: DeleteUploadedDocumentRequest
    ) -> None:

        await check_if_chat_exists(
            chat_id=request.chat_id,
            owner_id=request.owner_id,
            chat_session_repo=self._chat_session_repo,
        )

        document = await self._document_repo.get_by_criteria(
            criteria=DocumentSearchCriteria(
                id=request.document_id,
                session_id=request.chat_id,
            )
        )

        if document is None:
            raise not_found_error(
                message=(
                    f"Document with ID {request.document_id} "
                    f"was not found for chat {request.chat_id}."
                ),
                error_code="DOCUMENT_NOT_FOUND",
            )

        await self._document_repo.delete(request.document_id)

        self._logger.info(
            f"Document with ID {request.document_id} has been deleted from chat {request.chat_id}."
        )

    # ========================== HELPER METHODS ==========================

    @staticmethod
    def _normalize_filename(filename: str) -> str:
        return filename.strip().lower()

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
            self._normalize_filename(document.filename) # type: ignore
            for document in existing_documents
            if document.filename # type: ignore
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
        """
        Read data from upload and return as bytes.
        """
        try:
            # Offload potentially blocking file read to a thread
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
        """
        Check if the total size of documents in a chat session,
        including incoming bytes, exceeds the maximum allowed size.
        """
        current_mb_in_chat = await self._document_repo.get_total_size_mb(
            chat_session_id=chat_session_id
        )
        current_bytes_in_chat = int(current_mb_in_chat * 1024 * 1024)
        return current_bytes_in_chat + incoming_bytes > _MAX_FILES_PER_CHAT_BYTES
