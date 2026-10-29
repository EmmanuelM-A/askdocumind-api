import asyncio
import hashlib
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from src.exceptions import (
    conflict_error,
    object_storage_error,
    unprocessable_content_error,
)
from src.exceptions.base import ApiException
from src.uploads.storage.object_storage import ObjectStorage

# A dot followed by letters, digits and a few safe symbols, such as ".pdf" or
# ".tar.gz". Path separators are not allowed, so a suffix cannot move the
# downloaded file out of its temporary directory.
_SAFE_SUFFIX = re.compile(r"\.[A-Za-z0-9._+-]{1,31}")


def _calculate_checksum(file_path: Path) -> str:
    """
    Calculates the SHA256 checksum of the file at the given path.
    """
    with open(file_path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _normalize_suffix(suffix: str) -> str:
    """
    Return a safe file suffix with a leading dot, or an empty string.
    Raises a 422 error for a suffix with unsafe characters.
    """
    suffix = suffix.strip()

    if not suffix:
        return ""

    if not suffix.startswith("."):
        suffix = f".{suffix}"

    if not _SAFE_SUFFIX.fullmatch(suffix):
        raise unprocessable_content_error(
            message="The file suffix provided is invalid.",
            error_code="INVALID_FILE_SUFFIX",
        )

    return suffix


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

        The suffix gets a leading dot when it has none. The expected checksum
        is compared in lowercase with surrounding whitespace removed. Storage
        failures raise a 500 error, an invalid suffix raises a 422 error, and
        a checksum mismatch raises a 409 error. The temporary directory is
        removed when the context exits.
        """
        normalized_suffix = _normalize_suffix(suffix)
        expected = expected_checksum.strip().lower()

        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / f"download{normalized_suffix}"

            try:
                await asyncio.to_thread(
                    self._object_storage.download_to, object_key, file_path
                )
                digest = await asyncio.to_thread(_calculate_checksum, file_path)
            except ApiException:
                raise
            except Exception as e:
                raise object_storage_error(
                    message="The file could not be downloaded from object storage.",
                    error_details={"object_key": object_key},
                ) from e

            if digest != expected:
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
