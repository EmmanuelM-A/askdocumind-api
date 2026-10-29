import asyncio
import logging
from uuid import UUID

from src.database.session import DatabaseSessionManager
from src.rag.repository.chunk_embedding_repository_impl import (
    ChunkEmbeddingRepositoryImpl,
)
from src.rag.services.chunk.factory import ChunkerFactory
from src.rag.services.embed.embedder import Embedder
from src.rag.services.extract.extraction import Extraction
from src.rag.services.report.status_reporter import (
    ProcessingStatus,
    StatusConflict,
    StatusReporter,
    StatusReportFailed,
)
from src.rag.services.store import StorageJob, StoreChunkEmbeddingService
from src.rag.services.utils import RunGuard
from src.uploads.models.document import Document

_logger = logging.getLogger(__name__)


def build_job(document: Document) -> StorageJob:
    """
    Build a StorageJob from a Document instance.
    """
    return StorageJob(
        document_id=document.id,
        chat_session_id=document.chat_session_id,
        filename=document.original_filename,
        content_type=document.content_type,
        checksum=document.checksum,
        object_key=document.object_key,
    )


class IngestionRunner:
    """
    Service class responsible for handling the ingestion of documents into
    the RAG storage system.
    """

    def __init__(
        self,
        session_manager: DatabaseSessionManager,
        extraction: Extraction,
        chunker_factory: ChunkerFactory,
        embedder: Embedder,
        status_reporter: StatusReporter,
        guard: RunGuard,
        max_concurrent: int = 1,
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1.")

        self._session_manager = session_manager
        self._extraction = extraction
        self._chunker_factory = chunker_factory
        self._embedder = embedder
        self._status_reporter = status_reporter
        self._guard = guard
        # Shared by every run, so it caps ingestions across the whole app.
        self._slots = asyncio.Semaphore(max_concurrent)
        self._tasks: set[asyncio.Task] = set()

    def start(self, job: StorageJob) -> None:
        """
        Start an ingestion in the background and return at once.
        """
        task = asyncio.create_task(self._run(job), name=f"ingest-{job.document_id}")

        # The set keeps a reference so Python never collects a running task.
        self._tasks.add(task)

        task.add_done_callback(self._tasks.discard)

    async def _run(self, job: StorageJob) -> None:
        """
        Runs the ingestion for a given job. It ensures that only one
        ingestion runs for a given document at a time using the RunGuard.
        """
        if not self._guard.acquire(job.document_id):
            _logger.info(
                "The document '%s' is already being processed. Skipping...",
                job.document_id,
            )
            return

        try:
            async with self._slots:
                await self._ingest(job)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception("Unexpected ingestion error for '%s'", job.document_id)
        finally:
            self._guard.release(job.document_id)

    async def _ingest(self, job: StorageJob) -> None:
        # The chunks commit when this block ends. The document is only marked
        # as completed after that, so a completed document always has chunks.
        async with self._session_manager.get_session() as session:
            storage_service = StoreChunkEmbeddingService(
                extraction=self._extraction,
                chunker_factory=self._chunker_factory,
                embedder=self._embedder,
                chunk_embedding_repository=ChunkEmbeddingRepositoryImpl(session),
                status_reporter=self._status_reporter,
            )
            stored = await storage_service.run(job)

        if stored:
            await self._complete(job)

    async def _complete(self, job: StorageJob) -> None:
        try:
            await self._status_reporter.report(
                job.document_id, ProcessingStatus.COMPLETED
            )
        except StatusConflict:
            _logger.warning(
                "The document '%s' changed state during the run. Removing chunks.",
                job.document_id,
            )
            await self._safe_delete_chunks(job.document_id)
        except StatusReportFailed:
            # The document stays PROCESSING. The sweeper fails it and removes
            # its chunks once the processing timeout passes.
            _logger.error(
                "Failed to report the document '%s' as completed.",
                job.document_id,
            )

    async def _safe_delete_chunks(self, document_id: UUID) -> None:
        try:
            async with self._session_manager.get_session() as session:
                await ChunkEmbeddingRepositoryImpl(session).delete_by_document(
                    document_id=document_id
                )
        except Exception:
            _logger.exception(
                "Failed to delete chunk embeddings for document '%s'", document_id
            )

    async def shutdown(self) -> None:
        """
        Gracefully shutdown the ingestion service by cancelling all running
        ingestion tasks and waiting for them to finish.
        """
        for task in list(self._tasks):
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
