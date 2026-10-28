import logging
from collections.abc import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import DatabaseSessionManager
from src.rag.services.report.status_reporter import (
    ProcessingStatus,
    StatusConflict,
    StatusReportFailed,
    StatusReporter,
)
from src.uploads.domain.document import DocumentStatus
from src.uploads.repository.document_repository import DocumentRepository
from src.uploads.repository.document_repository_impl import DocumentRepositoryImpl

_logger = logging.getLogger(__name__)

# Matches the length of the documents.error_message column.
_MAX_ERROR_MESSAGE_CHARS = 512

_ALLOWED_FROM = {
    ProcessingStatus.PROCESSING: [DocumentStatus.UPLOADED],
    ProcessingStatus.COMPLETED: [DocumentStatus.PROCESSING],
    ProcessingStatus.FAILED: [DocumentStatus.PROCESSING],
}

DocumentRepositoryFactory = Callable[[AsyncSession], DocumentRepository]


def _clean_error_message(
    status: ProcessingStatus, error_message: str | None
) -> str | None:
    """
    Keep an error message only for FAILED, and make it safe to store.
    """
    if status is not ProcessingStatus.FAILED or not error_message:
        return None

    # PostgreSQL text columns reject NUL characters, and a rejected write
    # would leave the document stuck in PROCESSING.
    return error_message.replace("\x00", "")[:_MAX_ERROR_MESSAGE_CHARS]


class DocumentStatusReporter(StatusReporter):
    """
    A concrete implementation of StatusReporter for reporting the processing
    status of documents.
    """

    def __init__(
        self,
        session_manager: DatabaseSessionManager,
        repository_factory: DocumentRepositoryFactory = DocumentRepositoryImpl,
    ) -> None:
        self._session_manager = session_manager
        self._repository_factory = repository_factory

    async def report(
        self,
        document_id: UUID,
        status: ProcessingStatus,
        error_message: str | None = None,
    ) -> None:
        error_message = _clean_error_message(status, error_message)

        try:
            async with self._session_manager.get_session() as session:
                repository = self._repository_factory(session)
                transitioned = await repository.transition_document_status(
                    document_id=document_id,
                    from_statuses=_ALLOWED_FROM[status],
                    to_status=DocumentStatus(status.value),
                    error_message=error_message,
                )
        except Exception as exc:
            _logger.exception(
                "Failed to report status %s for document %s.",
                status.value,
                document_id,
            )
            raise StatusReportFailed(
                f"Failed to report status for document with ID: {document_id}"
            ) from exc

        if not transitioned:
            raise StatusConflict(
                f"Status transition for the document '{document_id}' failed."
            )
