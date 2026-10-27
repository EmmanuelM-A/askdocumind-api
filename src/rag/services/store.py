import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import TypeVar
from uuid import UUID

from src.config.configs import settings
from src.exceptions import unprocessable_content_error, ApiException
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
from src.rag.services.utils import StorageJob

_logger = logging.getLogger(__name__)

T = TypeVar("T")

_GENERIC_ERROR_MESSAGE = "PROCESSING_ERROR: The file could not be processed."


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
    Builds the message stored on a failed document. The client sees this
    message, so only ApiException text is used. Other exceptions, such as
    errors from the embedding provider, carry request details, so they get a
    generic message. The full error goes to the log.
    """
    if isinstance(exception, ApiException):
        return f"{exception.error_code}: {exception.detail}"

    return _GENERIC_ERROR_MESSAGE


class StoreChunkEmbeddingService:
    def __init__(
        self,
        extraction: Extraction,
        chunker_factory: ChunkerFactory,
        embedder: Embedder,
        chunk_embedding_repository: ChunkEmbeddingRepository,
        status_reporter: StatusReporter,
    ) -> None:
        self._extraction = extraction
        self._chunker_factory = chunker_factory
        self._embedder = embedder
        self._chunk_embedding_repository = chunk_embedding_repository
        self._status = status_reporter

    async def run(self, job: StorageJob) -> bool:
        """
        Claims the document, then extracts, chunks, embeds and stores its
        chunk embeddings. The chunks are only flushed, so the caller must
        commit the session before it marks the document as completed.

        :returns: True when the chunks are stored and the document is ready
            to be marked as completed. False when the document was skipped
            or failed.
        """
        # Phase 1: Claim the document.
        try:
            await self._status.report(
                document_id=job.document_id, status=ProcessingStatus.PROCESSING
            )
        except StatusConflict:
            _logger.info(
                "The document '%s' cannot be claimed. It is already being "
                "processed, finished or removed. Skipping...",
                job.document_id,
            )
            return False
        except StatusReportFailed:
            _logger.warning(
                "Could not report the processing status for the document "
                "'%s'. Skipping...",
                job.document_id,
            )
            return False

        # Phase 2: Process and store chunk embeddings for the document.
        try:
            await self._chunk_embedding_repository.delete_by_document(
                document_id=job.document_id
            )
            total_chunks, total_chars = await self._handle_storage(job)

            if total_chunks == 0:
                raise unprocessable_content_error(
                    message="No extractable text found.",
                    error_code="NO_CONTENT",
                )
            if total_chars < settings.rag.MIN_CONTENT_LENGTH:
                raise unprocessable_content_error(
                    message="The file has too little text.",
                    error_code="CONTENT_TOO_SHORT",
                )
        except Exception as exc:
            await self._handle_fail(job, exc)
            return False

        return True

    async def _handle_storage(self, job: StorageJob) -> tuple[int, int]:
        chunker = self._chunker_factory.get_chunker(job.extension)
        total_chunks = 0
        total_chars = 0

        # Each generator closes when the block ends, last opened first, so an
        # error or early exit releases the extractor and its temp file at once.
        async with (
            aclosing(self._extraction.stream(job)) as segments,
            aclosing(
                chunker.chunk_stream(stream=segments, source_id=job.document_id)
            ) as chunks,
            aclosing(
                _batch_items(chunks, settings.rag.PROCESSING_BATCH_SIZE)
            ) as batches,
        ):
            async for batch in batches:
                embeddings = await self._embedder.embed_chunks(batch)

                # Not an ApiException, so the client gets the generic message.
                if len(embeddings) != len(batch):
                    raise RuntimeError(
                        f"The embedder returned {len(embeddings)} embeddings "
                        f"for {len(batch)} chunks."
                    )

                await self._chunk_embedding_repository.create_many(
                    chunks=[
                        ChunkEmbedding(
                            document_id=job.document_id,
                            chat_session_id=job.chat_session_id,
                            chunk_index=chunk.index,
                            chunk_text=chunk.text,
                            embedding=embedding,
                        )
                        for chunk, embedding in zip(batch, embeddings, strict=True)
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
            await self._chunk_embedding_repository.delete_by_document(
                document_id=document_id
            )
        except Exception as exc:
            _logger.exception(
                "Failed to delete chunk embeddings for document '%s'",
                document_id,
                exc_info=exc,
            )
