import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import TypeVar
from uuid import UUID

from anyio import Semaphore

from src.config.configs import settings
from src.exceptions import conflict_error, unprocessable_content_error, ApiException
from src.rag.models.chunk_embedding import ChunkEmbedding
from src.rag.repository.chunk_embedding_repository import ChunkEmbeddingRepository
from src.rag.services.chunk.factory import ChunkerFactory
from src.rag.services.embed.embedder import Embedder
from src.rag.services.extract.extraction import Extraction
from src.rag.services.report.status_reporter import (
    StatusReporter,
    ProcessingStatus,
    StatusConflict,
    StatusReportFailed,
)
from src.rag.services.utils import RunGuard, StorageJob

_logger = logging.getLogger(__name__)

T = TypeVar("T")


async def _batch_items(items: AsyncIterator[T], size: int) -> AsyncIterator[list[T]]:
    """
    Groups items from an asynchronous iterator into batches of a specified size.
    """
    batch: list[T] = []

    async for item in items:
        batch.append(item)

        if len(batch) == size:
            yield batch
            batch = []

    if batch:
        yield batch


def _safe_message(exception: Exception) -> str:
    """
    Safely retrieves a message from an exception. If the exception is an
    instance of ApiException, it returns a formatted string with the error code
    and detail. Otherwise, it attempts to get the 'message' attribute of the
    exception, defaulting to a generic processing error message if not found.
    """
    if isinstance(exception, ApiException):
        code = exception.error_code
        message = exception.detail
        return f"{code}: {message}"

    return getattr(
        exception,
        "message",
        "PROCESSING_ERROR: The file could not be processed.",
    )


class StoreChunkEmbeddingService:
    def __init__(
        self,
        extraction: Extraction,
        chunker_factory: ChunkerFactory,
        embedder: Embedder,
        chunk_embedding_repository: ChunkEmbeddingRepository,
        status_reporter: StatusReporter,
        guard: RunGuard,
        max_concurrent: int = 1,
    ) -> None:
        self._extraction = extraction
        self._chunker_factory = chunker_factory
        self._embedder = embedder
        self.chunk_embedding_repository = chunk_embedding_repository
        self._status = status_reporter
        self._guard = guard
        self._slots = Semaphore(max_concurrent)

    async def run(self, job: StorageJob) -> None:
        """
        Runs the ingestion process for a given job. It ensures that only one
        ingestion process runs for a given document at a time using the
        RunGuard.
        """
        if not self._guard.acquire(job.document_id):
            _logger.info(
                "The document with the provided ID is already being "
                "processed. Skipping..."
            )
            return

        try:
            async with self._slots:
                await self._handle_processing_for(job)
        finally:
            self._guard.release(job.document_id)

    async def _handle_processing_for(self, job: StorageJob) -> None:
        """
        Processes the ingestion of a document/file into the storage system.
        """
        # Phase 1: Claim the document.
        try:
            await self._status.report(
                document_id=job.document_id, status=ProcessingStatus.PROCESSING
            )
        except StatusConflict:
            _logger.info(
                "The document with the provided ID is already being "
                "processed. Skipping..."
            )
            return
        except StatusReportFailed:
            _logger.info("Failed to report the processing status for document")
            return

        # Phase 2: Process and store chunk embeddings for the document.
        try:
            await self.chunk_embedding_repository.delete_by_document(
                document_id=job.document_id
            )
            total_chunks, total_chars = await self._handle_storage(job)

            if total_chunks == 0:
                raise unprocessable_content_error(
                    message="No extractable text found.",
                    error_code="NO_CONTENT",
                )
            if total_chars < settings.storage.MIN_CONTENT_LENGTH:
                raise unprocessable_content_error(
                    message="The file has too little text.",
                    error_code="CONTENT_TOO_SHORT",
                )
        except Exception as exc:
            await self._handle_fail(job, exc)
            return

        # Phase 3: finish.
        try:
            await self._status.report(job.document_id, ProcessingStatus.COMPLETED)
        except StatusConflict:
            _logger.warning(
                "The document with the provided ID changed state during the run. "
                "Removing chunks."
            )
            await self._handle_safe_delete(job.document_id)
        except StatusReportFailed:
            _logger.error(
                "Failed to report the document '%s' as completed.",
                job.document_id,
            )

    async def _handle_storage(self, job: StorageJob) -> tuple[int, int]:
        chunker = self._chunker_factory.get_chunker(job.extension)
        total_chunks = 0
        total_chars = 0

        async with aclosing(self._extraction.stream(job)) as segments:
            chunk_stream = chunker.chunk_stream(
                stream=segments, source_id=job.document_id
            )

            async with aclosing(chunk_stream) as chunks:
                async for batch in _batch_items(
                    chunks, settings.rag.PROCESSING_BATCH_SIZE
                ):
                    embeddings = await self._embedder.embed_chunks(batch)

                    if len(embeddings) != len(batch):
                        raise conflict_error(
                            message="Mismatch between number of chunks and "
                            "embeddings.",
                            error_code="COUNT_MISMATCH",
                        )

                    await self.chunk_embedding_repository.create_many(
                        chunks=[
                            ChunkEmbedding(
                                document_id=job.document_id,
                                chat_session_id=job.chat_session_id,
                                chunk_index=chunk.index,
                                chunk_text=chunk.text,
                                embedding=embedding,
                            )
                            for chunk, embedding in zip(batch, embeddings)
                        ]
                    )

                    total_chunks += len(batch)
                    total_chars += sum(len(chunk.text) for chunk in batch)

        return total_chunks, total_chars

    async def _handle_fail(self, job: StorageJob, exc: Exception) -> None:
        _logger.exception(
            "Ingestion failed for the document '%s'", job.document_id, exc_info=exc
        )
        await self._handle_safe_delete(job.document_id)

        try:
            await self._status.report(
                job.document_id, ProcessingStatus.FAILED, _safe_message(exc)
            )
        except (StatusConflict, StatusReportFailed):
            _logger.exception(
                "An error occurred while reporting the failure for document '%s'",
                job.document_id,
            )

    async def _handle_safe_delete(self, document_id: UUID) -> None:
        try:
            await self.chunk_embedding_repository.delete_by_document(
                document_id=document_id
            )
        except Exception as exc:
            _logger.exception(
                "Failed to delete chunk embeddings for document '%s'",
                document_id,
                exc_info=exc,
            )
