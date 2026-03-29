"""
Service module for handling document uploads.
"""

import asyncio
from typing import List

from src.api.services.validation.rag_validation import (
    UploadDocumentsRequest,
    check_if_chat_exists,
    FetchUploadedDocumentsRequest,
    FetchDocumentMetadataRequest,
)
from src.api.utils.api_responses import SuccessResponseModel
from src.components.chatbot.core import RAGChatbot
from src.config.constants import ProcessingStatus
from src.database.models import Document
from src.database.repository.interfaces import (
    ChatSessionRepositoryInterface,
    DocumentRepositoryInterface,
)

from src.database.storage import StorageService
from src.errors.custom_exceptions import database_error
from src.logger.base_logger import BaseLogger


class UploadService:
    """Service class for handling document uploads."""

    def __init__(
        self,
        storage_service: StorageService,
        chat_session_repo: ChatSessionRepositoryInterface,
        document_repo: DocumentRepositoryInterface,
        chatbot: RAGChatbot,
    ) -> None:
        self.storage_service = storage_service
        self.chat_session_repo = chat_session_repo
        self.document_repo = document_repo
        self.chatbot = chatbot
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

        saved_keys: List[str] = []
        entities: List[Document] = []
        created_entities: List = []

        # 1) Persist files to storage and build Document entities
        for upload in request.documents:
            key = f"{request.chat_id}/{upload.filename}"

            try:
                # Offload potentially blocking file read to a thread
                data = await asyncio.to_thread(upload.file.read)

                # Persist data in storage (offload to thread if implementation is blocking)
                try:
                    await asyncio.to_thread(self.storage_service.save, key, data)
                except IOError as storage_exc:
                    # Attempt to clean up any files we already saved
                    for k in saved_keys:
                        try:
                            await asyncio.to_thread(self.storage_service.delete, k)
                        except (FileNotFoundError, IOError):
                            # Best-effort cleanup; ignore further errors
                            pass

                    raise database_error(
                        message=f"Failed to store document {upload.filename}",
                        error_code="DOCUMENT_STORAGE_FAILED",
                        stack_trace=str(storage_exc),
                    )

                # Track saved keys for cleanup if anything fails later
                saved_keys.append(key)
                self._logger.debug(
                    f"The key {key} was saved to storage file successfully"
                )

                # Build DB model instance; initially mark as PENDING until
                # vectors are verified/persisted to the vector store.
                entities.append(
                    Document(
                        session_id=request.chat_id,
                        filename=upload.filename,
                        file_size=len(data),
                        vector_id=request.vector_id,
                        processing_status=ProcessingStatus.PENDING,
                    )
                )

                # Reset the file pointer so the downstream processor can re-read
                # the same upload when creating vectors. Use thread to avoid
                # blocking the event loop if seek blocks.
                try:
                    await asyncio.to_thread(upload.file.seek, 0)
                # except asyncio.CancelledError:
                #     raise
                # except (ValueError, OSError) as e:
                #     throw_unprocessable_entity_error(
                #         f"Failed to seek uploaded file to start because {e}",
                #         "SEEK_FAILED"
                #     )
                except (ValueError, OSError):
                    # If seek is not supported, vector processing may still work if
                    # the extractor can handle bytes or a fresh UploadFile. We
                    # continue and let the vector processor surface errors.
                    pass

            except Exception as e:
                # Attempt to clean up any files we already saved
                for k in saved_keys:
                    try:
                        await asyncio.to_thread(self.storage_service.delete, k)
                    except Exception:
                        # Best-effort cleanup; ignore further errors
                        pass

                raise database_error(
                    message=f"Failed to process uploaded file {upload.filename}",
                    error_code="DOCUMENT_READ_FAILED",
                    stack_trace=str(e),
                )

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
            # Clean up saved files; vector store may have partially written data
            for k in saved_keys:
                try:
                    await asyncio.to_thread(self.storage_service.delete, k)
                except Exception:
                    pass

            raise database_error(
                message="Failed to process and save document vectors",
                error_code="VECTOR_PROCESSING_FAILED",
                stack_trace=str(e),
            )

        # 3) Store document metadata in the database
        try:
            created_entities = await self.document_repo.create_many(entities=entities)
        except Exception as e:
            # Persisted files are removed (best-effort). We cannot guarantee
            # vector-store rollback here with the current API.
            for k in saved_keys:
                try:
                    await asyncio.to_thread(self.storage_service.delete, k)
                except Exception:
                    pass

            raise database_error(
                message="Failed to store document metadata in the database",
                error_code="DOCUMENT_METADATA_STORAGE_FAILED",
                stack_trace=str(e),
            )

        if not created_entities or len(created_entities) != len(entities):
            # Best-effort cleanup of stored files if counts mismatch
            for k in saved_keys:
                try:
                    await asyncio.to_thread(self.storage_service.delete, k)
                except Exception:
                    pass

            raise database_error(
                message="Failed to store document metadata in the database",
                error_code="DOCUMENT_METADATA_STORAGE_FAILED",
                error_details="Mismatch in number of created document entities",
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

        # Fetch each requested document and verify ownership
        metadata_list = []
        for doc_id in request.document_ids:
            doc = await self.document_repo.get_by_id(doc_id)

            if not doc:
                continue

            if doc.session_id != request.chat_id:
                self._logger.warning(
                    f"The document {doc} does not belong to chat "
                    f"{request.chat_id}, skipping..."
                )
                continue

            metadata_list.append(doc.to_json())

        return SuccessResponseModel(
            message="Document metadata fetched successfully.",
            data=metadata_list,
        )
