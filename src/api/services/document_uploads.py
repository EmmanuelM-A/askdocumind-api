"""
Service module for handling document uploads.
"""

import asyncio
from typing import List, Tuple
from uuid import UUID

from src.api.services.validation.rag_validation import (
    UploadDocumentsRequest,
    check_if_chat_exists,
    FetchUploadedDocumentsRequest,
    FetchDocumentMetadataRequest,
)
from src.api.utils.api_responses import SuccessResponseModel
from src.components.chatbot.core import RAGChatbot
from src.config.configs import settings
from src.config.constants import ProcessingStatus
from src.database.models import Document
from src.database.repository.interfaces import (
    ChatSessionRepositoryInterface,
    DocumentRepositoryInterface,
    DocumentSearchCriteria,
    DBTransactionFactory,
)

from src.database.storage import StorageService
from src.errors.api_exceptions import ApiException
from src.errors.custom_exceptions import database_error, unprocessable_entity_error
from src.logger.base_logger import BaseLogger


class UploadService:
    """Service class for handling document uploads."""

    def __init__(
        self,
        storage_service: StorageService,
        chat_session_repo: ChatSessionRepositoryInterface,
        document_repo: DocumentRepositoryInterface,
        chatbot: RAGChatbot,
        tx_factory: DBTransactionFactory,
    ) -> None:
        self.storage_service = storage_service
        self.chat_session_repo = chat_session_repo
        self.document_repo = document_repo
        self.chatbot = chatbot
        self.tx_factory = tx_factory
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
            chat_id=request.chat_id,
            chat_session_repo=self.chat_session_repo,
            chatbot=self.chatbot,
        )

        self._logger.debug(
            f"The chat {request.chat_id} has been validated successfully"
        )

        existing_documents_count = await self.document_repo.count(
            filter_id=request.chat_id
        )
        incoming_documents_count = len(request.documents)
        max_documents_per_chat = settings.server.MAX_DOCUMENTS_PER_CHAT

        if existing_documents_count + incoming_documents_count > max_documents_per_chat:
            raise unprocessable_entity_error(
                message=(
                    "Document upload limit reached for this chat. "
                    f"Maximum allowed documents: {max_documents_per_chat}."
                ),
                error_code="CHAT_DOCUMENT_LIMIT_REACHED",
            )

        saved_keys, entities = await self._persist_files_to_storage(request)

        # Persist metadata first so vector-processing failures can be marked as FAILED.
        try:
            async with self.tx_factory.create() as tx:
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

        try:
            await self._process_uploaded_files(request, saved_keys)
        except ApiException:
            await self._update_document_statuses(
                document_ids=created_entities,
                status=ProcessingStatus.FAILED,
            )
            raise

        await self._update_document_statuses(
            document_ids=created_entities,
            status=ProcessingStatus.COMPLETED,
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
            chat_id=request.chat_id,
            chat_session_repo=self.chat_session_repo,
            chatbot=self.chatbot,
        )

        documents = await self.document_repo.list_by(
            criteria=DocumentSearchCriteria(session_id=request.chat_id)
        )

        metadata_list = [document.to_dict() for document in documents]

        return SuccessResponseModel(
            message="Document metadata fetched successfully.",
            data=metadata_list,
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

    async def _persist_files_to_storage(
        self,
        request: UploadDocumentsRequest,
    ) -> Tuple[List[str], List[Document]]:
        saved_keys: List[str] = []
        entities: List[Document] = []
        max_file_size_bytes = settings.files.MAX_FILE_SIZE_MB * 1024 * 1024

        for upload in request.documents:
            key = f"{request.chat_id}/{upload.filename}"

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

            if len(data) > max_file_size_bytes:
                raise unprocessable_entity_error(
                    message=(
                        f"File '{upload.filename}' exceeds the maximum size of "
                        f"{settings.files.MAX_FILE_SIZE_MB} MB."
                    ),
                    error_code="FILE_SIZE_LIMIT_EXCEEDED",
                )

            # Persist data in storage (offload to thread if implementation is blocking)
            try:
                await asyncio.to_thread(self.storage_service.save, key, data)
            except IOError as storage_exc:
                await self._cleanup_saved_files_if_storage_failed(saved_keys)

                raise database_error(
                    message=f"Failed to store document {upload.filename}",
                    error_code="DOCUMENT_STORAGE_FAILED",
                    stack_trace=str(storage_exc),
                )

            # Track saved keys for cleanup if anything fails later
            saved_keys.append(key)
            self._logger.debug(f"The key {key} was saved to storage file successfully")

            # Build DB model instance; initially mark as PROCESSING while
            # vectors are being verified/persisted to the vector store.
            entities.append(
                Document(
                    session_id=request.chat_id,
                    filename=upload.filename,
                    file_size=len(data),
                    vector_id=request.chat_id,
                    processing_status=ProcessingStatus.PROCESSING,
                )
            )

            # Reset the file pointer so the downstream processor can re-read
            # the same upload when creating vectors.
            try:
                await asyncio.to_thread(upload.file.seek, 0)
            except (ValueError, OSError):
                # If seek is not supported, vector processing may still work if
                # the extractor can handle bytes or a fresh UploadFile. We
                # continue and let the vector processor surface errors.
                pass

        return saved_keys, entities

    async def _process_uploaded_files(
        self,
        request: UploadDocumentsRequest,
        saved_keys: List[str],
    ) -> None:
        # 2) Process and save document vectors (best-effort cleanup on failure)
        try:
            # Offload the synchronous vector processing to a thread so the event loop
            # isn't blocked by CPU/IO-heavy processing in the embedding pipeline.
            await asyncio.to_thread(
                self.chatbot.process_and_save_vectors,
                request.documents,
                str(request.chat_id),
            )
        except Exception as e:
            await self._cleanup_saved_files_if_storage_failed(saved_keys)

            raise database_error(
                message="Failed to process and save document vectors",
                error_code="VECTOR_PROCESSING_FAILED",
                stack_trace=str(e),
            )

    async def _update_document_statuses(
        self,
        document_ids: List[UUID],
        status: ProcessingStatus,
    ) -> None:
        if not document_ids:
            return

        try:
            async with self.tx_factory.create() as tx:
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

