import asyncio
import hashlib
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from httpx import AsyncClient, HTTPStatusError, HTTPError

from src.exceptions import content_too_large_error, server_error, \
    conflict_error


class S3FileDownloader:
    """
    Downloads files from S3 or any HTTP endpoint, ensuring that the
    downloaded file does not exceed a specified maximum size and that its
    checksum matches an expected value.
    """

    def __init__(self, max_bytes: int, chunk_bytes: int, timeout: float) -> None:
        self._max_bytes = max_bytes
        self._chunk_bytes = chunk_bytes
        self._timeout = timeout

    @asynccontextmanager
    async def download(
        self, url: str, expected_checksum: str, suffix: str = ""
    ) -> AsyncIterator[Path]:
        hasher = hashlib.sha256()
        size = 0

        with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
            try:
                async with AsyncClient(timeout=self._timeout) as client:
                    async with client.stream("GET", url) as response:
                        response.raise_for_status()

                        declared = int(response.headers.get("content-length", 0))
                        if declared > self._max_bytes:
                            raise content_too_large_error(
                                message="The file downloaded has exceeded the "
                                        "maximum allowed size.",
                                error_code="FILE_TOO_LARGE",
                            )

                        async for block in response.aiter_bytes(self._chunk_bytes):
                            size += len(block)
                            if size > self._max_bytes:
                                raise content_too_large_error(
                                    message="The file downloading has exceeded the "
                                            "maximum allowed size.",
                                    error_code="FILE_TOO_LARGE",
                                )

                            hasher.update(block)
                            await asyncio.to_thread(tmp.write, block)

            except HTTPStatusError as exc:
                raise server_error(
                    message="An error occurred while downloading the file.",
                    error_code="DOWNLOAD_ERROR",
                    error_details={
                        "url": url,
                    },
                    cause=exc
                ) from exc
            except HTTPError:
                raise server_error(
                    message="An error occurred while downloading the file.",
                    error_code="DOWNLOAD_ERROR",
                    error_details={
                        "url": url,
                    }
                )

            tmp.flush()

            if hasher.hexdigest() != expected_checksum:
                raise conflict_error(
                    message="The file downloaded's checksum does not match "
                            "the expected checksum.",
                    error_code="CHECKSUM_MISMATCH",
                    error_details={
                        "url": url
                    }
                )

            yield Path(tmp.name)
