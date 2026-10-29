from enum import Enum


class DocumentStatus(str, Enum):
    """
    Enum representing the various statuses a document can have during
    its lifecycle.
    """

    PENDING = "PENDING"
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
