from pathlib import Path
from uuid import UUID

from pydantic import BaseModel


class StorageJob(BaseModel):
    """
    Represents a job request payload to process and store a document/file
    as embeddings in the storage system.
    """

    document_id: UUID
    chat_session_id: UUID
    filename: str
    content_type: str
    checksum: str
    object_key: str

    @property
    def extension(self) -> str:
        return Path(self.filename).suffix.lower()


class RunGuard:
    """
    A guard to ensure that only one ingestion process runs for a given
    document at a time.
    """

    def __init__(self) -> None:
        self._active: set[UUID] = set()

    def acquire(self, document_id: UUID) -> bool:
        """
        Attempts to acquire a lock for the given document ID. If the
        document is already being processed, it returns False. Otherwise,
        it adds the document ID to the active set
        """
        if document_id in self._active:
            return False

        self._active.add(document_id)

        return True

    def release(self, document_id: UUID) -> None:
        """
        Releases the lock for the given document ID, allowing other
        ingestion processes to proceed.
        """
        self._active.discard(document_id)
