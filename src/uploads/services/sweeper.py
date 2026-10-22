import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.database.session import DatabaseSessionManager
from src.rag.repository.chunk_embedding_repository_impl import (
    ChunkEmbeddingRepositoryImpl,
)

from src.uploads.domain.document import DocumentStatus
from src.uploads.models.document import Document
from src.uploads.repository.document_repository import DocumentRepository
from src.uploads.repository.document_repository_impl import DocumentRepositoryImpl
from src.uploads.services.ingestion_service import IngestionRunner, build_job
from src.uploads.storage.object_storage import ObjectStorage

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SweeperConfig:
    processing_timeout_seconds: int = 3600
    interval_seconds: int = 60
    uploaded_retry_after_seconds: int = 120
    uploaded_max_age_seconds: int = 3600
    pending_after_seconds: int = 600
    batch_limit: int = 50


class Sweeper:
    def __init__(
        self,
        session_manager: DatabaseSessionManager,
        storage: ObjectStorage,
        runner: IngestionRunner,
        config: SweeperConfig,
    ) -> None:
        self._session_manager = session_manager
        self._storage = storage
        self._runner = runner
        self._config = config
        self._task: asyncio.Task | None = None

    # ------------------------ Lifecycle ------------------------

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="upload-sweeper")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.sweep_once()
            except Exception:
                _logger.exception("The sweeper pass failed.")
            await asyncio.sleep(self._config.interval_seconds)

    async def sweep_once(self) -> None:
        # The order matters. Rule 1 fails the oldest UPLOADED rows before
        # rule 2 looks for rows to retry.
        rules = (
            self._fail_expired_uploaded,
            self._retry_stuck_uploaded,
            self._fail_timed_out_processing,
            self._remove_abandoned_pending,
        )
        for rule in rules:
            try:
                await rule()
            except Exception:
                _logger.exception("Sweeper rule '%s' failed.", rule.__name__)

    # ------------------------ Rules ------------------------

    async def _fail_expired_uploaded(self) -> None:
        """Rule 1: processing never started and the retry window is over."""
        async with self._session_manager.get_session() as session:
            repository = DocumentRepositoryImpl(session)

            for doc in await self._find_stale(
                repository=repository,
                status=DocumentStatus.UPLOADED,
                older_than_seconds=self._config.uploaded_max_age_seconds,
            ):
                await repository.transition_document_status(
                    doc.id,
                    [DocumentStatus.UPLOADED],
                    DocumentStatus.FAILED,
                    "UPLOAD_STALE: Processing never started.",
                )

    async def _retry_stuck_uploaded(self) -> None:
        """Rule 2: the first trigger was lost, so start the ingestion again."""
        async with self._session_manager.get_session() as session:
            repository = DocumentRepositoryImpl(session)

            for doc in await self._find_stale(
                repository=repository,
                status=DocumentStatus.UPLOADED,
                older_than_seconds=self._config.uploaded_retry_after_seconds,
            ):
                # The run guard drops this call when a run for the same
                # document is already active or waiting for a slot.
                self._runner.start(build_job(doc))

    async def _fail_timed_out_processing(self) -> None:
        """Rule 3: a run died or hung, so fail the row and remove partial chunks."""
        async with self._session_manager.get_session() as session:
            documents = DocumentRepositoryImpl(session)
            chunks = ChunkEmbeddingRepositoryImpl(session)

            for doc in await self._find_stale(
                documents,
                DocumentStatus.PROCESSING,
                self._config.processing_timeout_seconds,
            ):
                moved = await documents.transition_document_status(
                    doc.id,
                    [DocumentStatus.PROCESSING],
                    DocumentStatus.FAILED,
                    "PROCESSING_TIMEOUT: Processing took too long.",
                )
                if moved:
                    await chunks.delete_by_document(document_id=doc.id)

    async def _remove_abandoned_pending(self) -> None:
        """Rule 4: an upload request died before the file finished storing."""
        async with self._session_manager.get_session() as session:
            documents = DocumentRepositoryImpl(session)

            for doc in await self._find_stale(
                documents, DocumentStatus.PENDING, self._config.pending_after_seconds
            ):
                # Claim the row first. A slow upload which still finishes
                # then fails its own PENDING -> UPLOADED step and cleans up.
                claimed = await documents.transition_document_status(
                    doc.id,
                    [DocumentStatus.PENDING],
                    DocumentStatus.FAILED,
                    "UPLOAD_ABANDONED: The upload did not finish.",
                )
                if not claimed:
                    continue

                await asyncio.to_thread(self._storage.delete, doc.object_key)
                await documents.delete(doc.id)

    # ------------------------ Helper ------------------------

    async def _find_stale(
        self,
        repository: DocumentRepository,
        status: DocumentStatus,
        older_than_seconds: int,
    ) -> list[Document]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)

        return await repository.list_stale_documents(
            status, cutoff, self._config.batch_limit
        )
