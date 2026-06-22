"""
Background cleanup service for stuck-PROCESSING documents and orphaned web chunks.
"""

from datetime import datetime, timedelta, timezone

from src.config.configs import settings
from src.config.constants import ProcessingStatus
from src.database.repository.interfaces import (
    DocumentRepositoryInterface,
    DocumentChunkRepositoryInterface,
)
from src.logger.base_logger import BaseLogger


class DocumentCleanupService:
    """
    Handles periodic cleanup of stuck documents and orphaned web-search chunks.
    """

    def __init__(
        self,
        document_repo: DocumentRepositoryInterface,
        chunk_repo: DocumentChunkRepositoryInterface,
    ) -> None:
        self._document_repo = document_repo
        self._chunk_repo = chunk_repo
        self._logger = BaseLogger(__name__)

    async def mark_stuck_documents_as_failed(
        self, batch_size: int = settings.files.DOC_CLEANUP_BATCH_SIZE
    ) -> int:
        """
        Find documents stuck in PROCESSING beyond the configured timeout and
        mark them as FAILED in batches.
        """

        cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=settings.files.STUCK_PROCESSING_TIMEOUT_MINS
        )

        stuck_ids = await self._document_repo.get_stuck_processing_ids(cutoff=cutoff)

        if not stuck_ids:
            self._logger.info("No stuck processing documents found.")
            return 0

        self._logger.debug(f"Found {len(stuck_ids)} stuck document(s) to mark as FAILED.")

        total_updated = 0
        failed_batches = 0

        for i in range(0, len(stuck_ids), batch_size):
            batch = stuck_ids[i : i + batch_size]
            try:
                total_updated += await self._document_repo.bulk_update_processing_status(
                    document_ids=batch,
                    status=ProcessingStatus.FAILED,
                )
            except Exception as exc:
                failed_batches += len(batch)
                self._logger.warning(
                    f"Failed to mark stuck-doc batch {i // batch_size + 1} as FAILED: {exc}"
                )

        self._logger.info(
            f"Marked {total_updated} stuck document(s) as FAILED, {failed_batches} failed."
        )
        return total_updated

    async def delete_failed_documents(
        self, batch_size: int = settings.files.DOC_CLEANUP_BATCH_SIZE
    ) -> int:
        """
        Delete FAILED documents (and their chunks via cascade) that have been
        in FAILED status for at least FAILED_DOC_TTL_H hours, in batches.
        """

        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=settings.files.FAILED_DOC_TTL_H
        )

        failed_ids = await self._document_repo.get_all_failed_ids(cutoff=cutoff)

        if not failed_ids:
            self._logger.info("No expired failed documents found.")
            return 0

        self._logger.debug(f"Found {len(failed_ids)} expired FAILED document(s) to delete.")

        total_deleted = 0
        failed_batches = 0

        for i in range(0, len(failed_ids), batch_size):
            batch = failed_ids[i : i + batch_size]
            try:
                total_deleted += await self._document_repo.delete_many(batch)
            except Exception as exc:
                failed_batches += len(batch)
                self._logger.warning(
                    f"Failed to delete FAILED-doc batch {i // batch_size + 1}: {exc}"
                )

        self._logger.info(
            f"Deleted {total_deleted} expired FAILED document(s), {failed_batches} failed."
        )
        return total_deleted

    async def delete_orphaned_web_chunks(self) -> int:
        """
        Delete web-search chunks (document_id IS NULL) older than WEB_CHUNK_TTL_H hours.
        """

        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=settings.files.WEB_CHUNK_TTL_H
        )

        try:
            deleted = await self._chunk_repo.delete_orphaned_web_chunks(cutoff=cutoff)
            self._logger.info(f"Deleted {deleted} orphaned web chunk(s).")
            return deleted
        except Exception as exc:
            self._logger.warning(f"Failed to delete orphaned web chunks: {exc}")
            return 0
