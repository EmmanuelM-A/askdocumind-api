import asyncio
import logging
from enum import Enum
from uuid import UUID

from httpx import AsyncClient, HTTPError
from pydantic import BaseModel


class ProcessingStatus(str, Enum):
    """
    Enum representing the processing status of a document/file.
    """

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ReportStatus(BaseModel):
    """
    Pydantic model representing the status report for a document/file.
    """

    status: ProcessingStatus
    error_message: str | None = None

    def to_dict(self) -> dict:
        """
        Converts the ReportStatus instance to a dictionary.
        """
        return {
            "status": self.status.value,
            "error_message": self.error_message,
        }

    @staticmethod
    def from_dict(data: dict) -> "ReportStatus":
        """
        Creates a ReportStatus instance from a dictionary.
        """
        return ReportStatus(
            status=ProcessingStatus(data["status"]),
            error_message=data.get("error_message"),
        )


class StatusConflict(Exception):
    """The upload service rejected the status change."""


class StatusReportFailed(Exception):
    """The status change never reached the upload service."""


# Same length as the database column for error messages
_MAX_LENGTH_ERROR_MESSAGE = 512

_logger = logging.getLogger(__name__)


class StatusReporter:
    """
    Responsible for reporting the processing status of a document/file to
    the upload service.
    """

    def __init__(
        self,
        client: AsyncClient,
        base_url: str,
        attempts: int = 3,
        base_delay_seconds: float = 0.5,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._attempts = attempts
        self._base_delay = base_delay_seconds

    async def report(
        self,
        document_id: UUID,
        status: ProcessingStatus,
        error_message: str | None = None,
    ) -> None:
        url = f"{self._base_url}/internal/uploads/{document_id}/status"

        error_message = (
            error_message[:_MAX_LENGTH_ERROR_MESSAGE] if error_message else None
        )

        body = ReportStatus(status=status, error_message=error_message).to_dict()

        for attempt in range(1, self._attempts + 1):
            try:
                response = await self._client.post(url, json=body)
            except HTTPError:
                response = None

            if response is not None:
                if response.is_success:
                    _logger.info("Successfully reported the status of the document.")
                    return
                if response.status_code == 409:
                    raise StatusConflict(
                        "The upload service rejected the status change due "
                        "to duplicate requests."
                    )
                if response.status_code < 500:
                    raise StatusReportFailed(
                        "An error occurred while reporting the status of the "
                        "document. "
                    )

            _logger.warning(
                "Reporting the status of the document failed. "
                "Retrying after cooldown..."
            )

            if attempt < self._attempts:
                await asyncio.sleep(self._base_delay * 2 ** (attempt - 1))

        raise StatusReportFailed(
            "Failed to report the status of the document after multiple "
            "attempts. Service may be unavailable or experiencing issues."
        )
