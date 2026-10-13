from uuid import UUID

from src.database.dependencies import DbSession
from src.rag.services.report.status_reporter import (
    StatusReporter,
    ProcessingStatus,
    StatusReportFailed,
    StatusConflict,
)
from src.uploads.dependencies import get_document_repository
from src.uploads.domain.document import DocumentStatus
from src.uploads.repository.document_repository import DocumentRepository

_ALLOWED_FROM = {
    ProcessingStatus.PROCESSING: [DocumentStatus.UPLOADED],
    ProcessingStatus.COMPLETED: [DocumentStatus.PROCESSING],
    ProcessingStatus.FAILED: [DocumentStatus.PROCESSING],
}


class DocumentStatusReporter(StatusReporter):
    """
    A concrete implementation of StatusReporter for reporting the processing
    status of documents.
    """

    def __init__(self, document_repository: DocumentRepository) -> None:
        self._document_repository = document_repository

    async def report(
        self,
        document_id: UUID,
        status: ProcessingStatus,
        error_message: str | None = None,
    ) -> None:

        if error_message and len(error_message) > 512:
            error_message = error_message[:512]

        try:
            async with DbSession as session:
                repository = get_document_repository(session)

                transitioned = await repository.transition_document_status(
                    document_id=document_id,
                    from_statuses=_ALLOWED_FROM[status],
                    to_status=DocumentStatus(status.value),
                    error_message=error_message,
                )
        except Exception:
            raise StatusReportFailed(
                f"Failed to report status for document with ID: {document_id}"
            )

        if not transitioned:
            raise StatusConflict(
                f"Status transition for the document '{document_id}' failed."
            )
