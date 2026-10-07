from enum import Enum


class ProcessingStatus(Enum):
    """Enum representing the processing status of a document."""

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
