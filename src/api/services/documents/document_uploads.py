"""
Service module for handling document uploads.
"""

import asyncio
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import UploadFile

from src.api.services.validation.rag_validation import (
    UploadDocumentsRequest,
    check_if_chat_exists,
    FetchUploadedDocumentsRequest,
    FetchDocumentMetadataRequest,
    DeleteUploadedDocumentRequest,
)
from src.api.utils.api_responses import SuccessResponseModel
from src.components.ingestion.vector_processor import VectorProcessor
from src.config.configs import settings
from src.config.constants import ProcessingStatus
from src.database.models import Document
from src.database.repository.interfaces import (
    ChatSessionRepositoryInterface,
    DocumentRepositoryInterface,
    DocumentSearchCriteria,
    DBTransaction,
    DBTransactionFactory,
)

from src.database.storage import StorageService
from src.errors.api_exceptions import ApiException
from src.errors.custom_exceptions import (
    conflict_error,
    database_error,
    unprocessable_entity_error,
    not_found_error,
)
from src.logger.base_logger import BaseLogger


class UploadService:
    """Service class for handling document uploads."""

    def __init__(
        self,
        storage_service: StorageService,
        vector_processor: VectorProcessor,
        chat_session_repo: ChatSessionRepositoryInterface,
        document_repo: DocumentRepositoryInterface,
        tx_factory: DBTransactionFactory,
    ) -> None:
        self.storage_service = storage_service
        self.vector_processor = vector_processor
        self.chat_session_repo = chat_session_repo
        self.document_repo = document_repo
        self.tx_factory = tx_factory

        self.max_file_size_bytes = settings.files.MAX_FILE_SIZE_MB * 1024 * 1024
        self.max_files_per_chat_bytes = (
            settings.files.MAX_FILES_PER_CHAT_MB * 1024 * 1024
        )

        self._logger = BaseLogger(__name__)

    async def handle_document_uploads(
        self, request: UploadDocumentsRequest
    ) -> SuccessResponseModel:
        """Handles document upload requests.

        Implementation notes / guarantees:
        - Validates that the chat exists (both DB session and vector index).
        - Persists each uploaded file to the configured storage backend.
        - Resets file pointers so the downstream vector-processing pipeline can
          re-read uploads reliably.
        - Processes documents into vectors and saves them to the vector store.
        - Persists document metadata in the database in a single batch.

        Cleanup behaviour:
        - If storage saving fails for any file the method attempts to remove any
          previously saved files and raises an API error.
        - If vector processing or DB persistence fails the method attempts to
          remove any saved files (best-effort). It is not possible to fully
          roll back vector store inserts with the current vector store API,
          so vector cleanup is best-effort or needs to be handled at a lower
          level if atomicity is required across services.
        """

        await check_if_chat_exists(
            chat_id=request.chat_id, chat_session_repo=self.chat_session_repo
        )

        self._logger.debug(
            f"The chat {request.chat_id} has been validated successfully"
        )

        await self._assert_no_duplicate_uploads(request)

        saved_keys: List[str] = []
        entities: List[Document] = []
        documents: List[Tuple[UUID, str, bytes]] = []
        files_that_exceed_chat_limit: List[str] = []
        created_entities: List[UUID] = []

        try:
            async with self.tx_factory.create() as tx:
                for uploaded_file in request.documents:
                    data = await self._read_data_from_upload(uploaded_file, saved_keys)

                    incoming_bytes = len(data)
                    exceeds = await self._do_incoming_bytes_exceed_chat_limit(
                        chat_session_id=request.chat_id,
                        incoming_bytes=incoming_bytes,
                    )

                    if exceeds:
                        files_that_exceed_chat_limit.append(uploaded_file.filename)
                        continue

                    key = f"{request.chat_id}/{uploaded_file.filename}"

                    await self._persist_data_to_storage(
                        key=key,
                        data=data,
                        filename=uploaded_file.filename,
                        saved_keys=saved_keys,
                    )
                    saved_keys.append(key)

                    self._logger.debug(
                        f"The key {key} was saved to storage file successfully"
                    )

                    document = Document(
                        session_id=request.chat_id,
                        filename=uploaded_file.filename,
                        file_size=len(data),
                        processing_status=ProcessingStatus.PROCESSING,
                    )

                    entities.append(document)
                    documents.append((document.id, uploaded_file.filename, data))

                if len(files_that_exceed_chat_limit) == len(request.documents):
                    raise conflict_error(
                        message=(
                            "All uploaded documents exceed the maximum total chat size limit of "
                            f"{self.max_files_per_chat_bytes / (1024 * 1024):.1f} MB."
                        ),
                        error_code="ALL_DOCUMENTS_EXCEED_CHAT_LIMIT",
                    )

                await self.vector_processor.process_and_save_vectors_from_uploads(
                    chat_session_id=request.chat_id, documents=documents, tx=tx
                )

                created_entities = await self.document_repo.create_many(
                    entities=entities,
                    tx=tx,
                )

                if not created_entities or len(created_entities) != len(entities):
                    raise database_error(
                        message="Failed to store document metadata in the database",
                        error_code="DOCUMENT_METADATA_STORAGE_FAILED",
                        error_details="Mismatch in number of created document entities",
                    )

                await self._update_document_statuses(
                    document_ids=created_entities,
                    status=ProcessingStatus.COMPLETED,
                    tx=tx,
                )
        except ApiException:
            await self._cleanup_saved_files_if_storage_failed(saved_keys)
            raise
        except Exception as e:
            await self._cleanup_saved_files_if_storage_failed(saved_keys)
            raise database_error(
                message="Failed to store document metadata in the database",
                error_code="DOCUMENT_METADATA_STORAGE_FAILED",
                stack_trace=str(e),
            )

        self._logger.info(
            f"Successfully updated {len(created_entities)} documents to COMPLETED status"
        )

        return SuccessResponseModel(
            message="Documents uploaded and processed successfully.",
            data={"quantity_uploaded": len(created_entities)},
        )

    async def fetch_uploaded_documents(
        self, request: FetchUploadedDocumentsRequest
    ) -> SuccessResponseModel:
        """
        Fetches uploaded documents (raw bytes, base64-encoded) based on the request.
        """

    async def fetch_uploaded_document_metadata(
        self, request: FetchDocumentMetadataRequest
    ) -> SuccessResponseModel:
        """Fetches metadata of uploaded documents for given document IDs and chat.

        Ensures documents belong to the supplied chat_id.
        """

        await check_if_chat_exists(
            chat_id=request.chat_id, chat_session_repo=self.chat_session_repo
        )

        documents = await self.document_repo.list_by(
            criteria=DocumentSearchCriteria(session_id=request.chat_id)
        )

        metadata_list = [document.to_dict() for document in documents]

        return SuccessResponseModel(
            message="Document metadata fetched successfully.",
            data=metadata_list,
        )

    async def delete_uploaded_document(
        self, request: DeleteUploadedDocumentRequest
    ) -> SuccessResponseModel:
        await check_if_chat_exists(
            chat_id=request.chat_id, chat_session_repo=self.chat_session_repo
        )

        document = await self.document_repo.get_by_criteria(
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

        storage_key = f"{request.chat_id}/{document.filename}"

        try:
            async with self.tx_factory.create() as tx:
                deleted = await self.document_repo.delete(request.document_id, tx=tx)
                if not deleted:
                    raise not_found_error(
                        message=(
                            f"Document with ID {request.document_id} "
                            f"was not found for chat {request.chat_id}."
                        ),
                        error_code="DOCUMENT_NOT_FOUND",
                    )

            await asyncio.to_thread(self.storage_service.delete, storage_key)
        except FileNotFoundError:
            self._logger.warning(
                f"Document file '{document.filename}' was already missing from storage "
                f"for chat {request.chat_id}."
            )
        except Exception as e:
            raise database_error(
                message="Failed to delete uploaded document.",
                error_code="DOCUMENT_DELETE_FAILED",
                stack_trace=str(e),
            )

        return SuccessResponseModel(
            message="Document deleted successfully.",
            data={"document_id": str(request.document_id)},
        )

    # ========================== HELPER METHODS ==========================

    async def _cleanup_saved_files_if_storage_failed(
        self, saved_keys: List[str]
    ) -> None:
        for k in saved_keys:
            try:
                await asyncio.to_thread(self.storage_service.delete, k)
            except (FileNotFoundError, IOError):
                # Best-effort cleanup; ignore further errors
                self._logger.warning(
                    f"Failed to clean up storage key {k} after storage error."
                )

    @staticmethod
    def _normalize_filename(filename: str) -> str:
        return filename.strip().lower()

    async def _assert_no_duplicate_uploads(
        self, request: UploadDocumentsRequest
    ) -> None:
        incoming_by_normalized: dict[str, str] = {}
        duplicates_in_request: set[str] = set()

        for upload in request.documents:
            normalized = self._normalize_filename(upload.filename)
            if normalized in incoming_by_normalized:
                duplicates_in_request.add(upload.filename)
                duplicates_in_request.add(incoming_by_normalized[normalized])
            else:
                incoming_by_normalized[normalized] = upload.filename

        if duplicates_in_request:
            duplicate_list = ", ".join(sorted(duplicates_in_request))
            raise conflict_error(
                message=f"Duplicate document names in request: {duplicate_list}.",
                error_code="DUPLICATE_DOCUMENTS_IN_REQUEST",
            )

        existing_documents = await self.document_repo.list_by(
            criteria=DocumentSearchCriteria(session_id=request.chat_id)
        )
        existing_names = {
            self._normalize_filename(document.filename)
            for document in existing_documents
            if document.filename
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

    async def _read_data_from_upload(
        self, upload: UploadFile, saved_keys: List[str]
    ) -> bytes:
        """
        Read data from upload and return as bytes.
        """
        try:
            # Offload potentially blocking file read to a thread
            data = await asyncio.to_thread(upload.file.read)
        except (FileNotFoundError, IOError) as e:
            await self._cleanup_saved_files_if_storage_failed(saved_keys)
            raise database_error(
                message=f"Failed to process uploaded file {upload.filename}",
                error_code="DOCUMENT_READ_FAILED",
                stack_trace=str(e),
            )

        if len(data) > self.max_file_size_bytes:
            raise unprocessable_entity_error(
                message=(
                    f"File '{upload.filename}' exceeds the maximum size of "
                    f"{self.max_file_size_bytes / (1024 * 1024):.1f} MB."
                ),
                error_code="FILE_SIZE_LIMIT_EXCEEDED",
            )

        return data

    async def _persist_data_to_storage(
        self, key: str, data: bytes, saved_keys: List[str], filename: str
    ) -> None:
        """
        Persist data from upload and store in storage.
        """
        try:
            await asyncio.to_thread(self.storage_service.save, key, data)
        except IOError as storage_exc:
            await self._cleanup_saved_files_if_storage_failed(saved_keys)
            raise database_error(
                message=f"Failed to store document {filename}",
                error_code="DOCUMENT_STORAGE_FAILED",
                stack_trace=str(storage_exc),
            )

    async def _do_incoming_bytes_exceed_chat_limit(
        self, chat_session_id: UUID, incoming_bytes: int
    ) -> bool:
        current_mb_in_chat = await self.document_repo.get_total_size_mb(
            chat_session_id=chat_session_id
        )
        current_bytes_in_chat = int(current_mb_in_chat * 1024 * 1024)
        return current_bytes_in_chat + incoming_bytes > self.max_files_per_chat_bytes

    async def _update_document_statuses(
        self,
        document_ids: List[UUID],
        status: ProcessingStatus,
        tx: Optional[DBTransaction] = None,
    ) -> None:
        if not document_ids:
            return

        try:
            if tx is None:
                async with self.tx_factory.create() as tx:
                    updated_count = (
                        await self.document_repo.bulk_update_processing_status(
                            document_ids,
                            status,
                            tx=tx,
                        )
                    )

                    if updated_count != len(document_ids):
                        raise database_error(
                            message=f"Failed to update all document statuses to {status.value}",
                            error_code="DOCUMENT_STATUS_UPDATE_FAILED",
                            error_details=(
                                f"Expected to update {len(document_ids)} documents, "
                                f"but updated {updated_count}."
                            ),
                        )
                return

            updated_count = await self.document_repo.bulk_update_processing_status(
                document_ids,
                status,
                tx=tx,
            )

            if updated_count != len(document_ids):
                raise database_error(
                    message=f"Failed to update all document statuses to {status.value}",
                    error_code="DOCUMENT_STATUS_UPDATE_FAILED",
                    error_details=(
                        f"Expected to update {len(document_ids)} documents, "
                        f"but updated {updated_count}."
                    ),
                )
        except Exception as e:
            raise database_error(
                message=f"Failed to update document statuses to {status.value}",
                error_code="DOCUMENT_STATUS_UPDATE_FAILED",
                stack_trace=str(e),
            )
