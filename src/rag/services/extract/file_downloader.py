import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from src.exceptions import conflict_error
from src.uploads.storage.object_storage import ObjectStorage


def _calculate_checksum(file_path: Path) -> str:
    """
    Calculates the SHA256 checksum of the file at the given path.
    """
    with open(file_path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


class S3FileDownloader:
    """
    Downloads files from an S3-compatible object storage service, verifies
    their checksums, and provides a temporary file path for further
    processing.
    """

    def __init__(self, object_storage: ObjectStorage) -> None:
        self._object_storage = object_storage

    @asynccontextmanager
    async def download(
        self, object_key: str, expected_checksum: str, suffix: str = ""
    ) -> AsyncIterator[Path]:
        """
        Downloads a file from the specified object key, verifies its checksum,
        and saves the file to a temporary location with the given suffix.
        """
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / f"download{suffix}"

            await asyncio.to_thread(
                self._object_storage.download_to, object_key, file_path
            )

            digest = await asyncio.to_thread(_calculate_checksum, file_path)

            if digest != expected_checksum.lower():
                raise conflict_error(
                    message="The downloaded file's checksum does not match "
                    "the expected value.",
                    error_code="CHECKSUM_MISMATCH",
                    error_details={
                        "object_key": object_key,
                        "expected_checksum": expected_checksum,
                        "actual_checksum": digest,
                    },
                )

            yield file_path
