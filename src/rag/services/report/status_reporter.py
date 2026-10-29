from abc import ABC, abstractmethod
from enum import Enum
from uuid import UUID


class ProcessingStatus(str, Enum):
    """
    Enum representing the processing status of a document/file.
    """

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class StatusConflict(Exception):
    """The upload service rejected the status change."""


class StatusReportFailed(Exception):
    """The status change never reached the upload service."""


class StatusReporter(ABC):
    """
    Abstract base class for reporting the processing status of a document/file.
    """

    @abstractmethod
    async def report(
        self,
        document_id: UUID,
        status: ProcessingStatus,
        error_message: str | None = None,
    ) -> None:
        """
        Reports the processing status of a document/file to the upload service.
        :raises StatusConflict: When a duplicate row is detected in the database.
        :raises StatusReportFailed: When the database update fails.
        """
        raise NotImplementedError(
            "The method 'report' must be implemented in subclasses of StatusReporter."
        )
