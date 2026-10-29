"""
Unit tests for Extraction.

The downloader and the extractors are fakes. The real file handling is
covered by the downloader and extractor tests, so these tests check only
what Extraction itself does: the order of work, the hand-off of arguments,
and the cleanup when a stream ends early, fails or is canceled.

Error tests assert only the HTTP status code of the raised ApiException.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.exceptions import unprocessable_content_error
from src.exceptions.base import ApiException
from src.rag.services.extract.extraction import Extraction
from src.rag.services.extract.extractors.extractor import Segment
from src.rag.services.extract.extractors.factory import ExtractorFactory
from src.rag.services.utils import StorageJob

# ---------------------------------------------------------------------------
# Fakes and helpers
# ---------------------------------------------------------------------------


class FakeDownloader:
    """Records calls and tracks whether the download context was released."""

    def __init__(self, tmp_path):
        self._tmp_path = tmp_path
        self.calls = []
        self.released = 0

    @asynccontextmanager
    async def download(self, object_key, checksum):
        self.calls.append((object_key, checksum))
        path = self._tmp_path / "download"
        path.write_bytes(b"")
        try:
            yield path
        finally:
            self.released += 1


class FakeExtractor:
    """Yields the given segments and records when its generator is closed."""

    def __init__(self, segments=(), error=None, delay=0.0):
        self._segments = list(segments)
        self._error = error
        self._delay = delay
        self.paths = []
        self.closed = False
        # Holding the generator stops Python from closing it by itself,
        # so a test sees only a close that Extraction asks for.
        self._generators = []

    def extract(self, path):
        self.paths.append(path)
        generator = self._run()
        self._generators.append(generator)
        return generator

    def _run(self):
        try:
            for segment in self._segments:
                yield segment
                if self._delay:
                    time.sleep(self._delay)
            if self._error:
                raise self._error
        finally:
            self.closed = True


def make_job(filename="report.pdf"):
    return StorageJob(
        document_id=uuid4(),
        chat_session_id=uuid4(),
        filename=filename,
        content_type="application/octet-stream",
        checksum="abc123",
        object_key="uploads/key",
    )


def make_extraction(tmp_path, extractor):
    factory = MagicMock()
    factory.get_extractor.return_value = extractor
    downloader = FakeDownloader(tmp_path)
    return Extraction(downloader, factory), downloader, factory


def segments(*texts):
    return [Segment(text, page=i + 1) for i, text in enumerate(texts)]


# ---------------------------------------------------------------------------
# Core behaviour
# ---------------------------------------------------------------------------


class TestStreaming:

    @pytest.mark.asyncio
    async def test_segments_are_streamed_in_order(self, tmp_path):
        expected = segments("one", "two", "three")
        extraction, downloader, _ = make_extraction(tmp_path, FakeExtractor(expected))

        result = [s async for s in extraction.stream(make_job())]

        assert result == expected
        assert downloader.released == 1

    @pytest.mark.asyncio
    async def test_download_gets_the_object_key_and_checksum(self, tmp_path):
        extractor = FakeExtractor(segments("one"))
        extraction, downloader, _ = make_extraction(tmp_path, extractor)

        _ = [s async for s in extraction.stream(make_job())]

        assert downloader.calls == [("uploads/key", "abc123")]
        assert extractor.paths == [tmp_path / "download"]

    @pytest.mark.asyncio
    async def test_extractor_is_chosen_from_the_lowercased_extension(self, tmp_path):
        extraction, _, factory = make_extraction(
            tmp_path, FakeExtractor(segments("one"))
        )

        _ = [s async for s in extraction.stream(make_job("Report.PDF"))]

        factory.get_extractor.assert_called_once_with(".pdf")

    @pytest.mark.asyncio
    async def test_empty_extraction_yields_nothing(self, tmp_path):
        extraction, downloader, _ = make_extraction(tmp_path, FakeExtractor())

        result = [s async for s in extraction.stream(make_job())]

        assert result == []
        assert downloader.released == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:

    @pytest.mark.asyncio
    async def test_unsupported_extension_raises_422_before_any_download(self, tmp_path):
        downloader = FakeDownloader(tmp_path)
        extraction = Extraction(downloader, ExtractorFactory())

        for filename in ("tool.exe", "README", "archive.tar.gz"):
            with pytest.raises(ApiException) as exc_info:
                _ = [s async for s in extraction.stream(make_job(filename))]

            assert exc_info.value.status_code == 422

        assert downloader.calls == []

    @pytest.mark.asyncio
    async def test_extractor_error_reaches_the_caller_and_releases_the_download(
        self, tmp_path
    ):
        error = unprocessable_content_error(
            message="Bad file.", error_code="PDF_EXTRACTION_ERROR"
        )
        extractor = FakeExtractor(segments("one"), error=error)
        extraction, downloader, _ = make_extraction(tmp_path, extractor)
        received = []

        with pytest.raises(ApiException) as exc_info:
            async for segment in extraction.stream(make_job()):
                received.append(segment)

        assert exc_info.value.status_code == 422
        assert len(received) == 1
        assert downloader.released == 1


# ---------------------------------------------------------------------------
# Clean-up
# ---------------------------------------------------------------------------


class TestCleanup:

    @pytest.mark.asyncio
    async def test_stopping_early_closes_the_extractor_and_the_download(self, tmp_path):
        extractor = FakeExtractor(segments("one", "two", "three"))
        extraction, downloader, _ = make_extraction(tmp_path, extractor)

        stream = extraction.stream(make_job())
        first = await stream.__anext__()
        await stream.aclose()

        assert first.text == "one"
        assert extractor.closed is True
        assert downloader.released == 1

    @pytest.mark.asyncio
    async def test_cancelling_the_stream_releases_the_download(self, tmp_path):
        extractor = FakeExtractor(segments("one", "two"), delay=0.4)
        extraction, downloader, _ = make_extraction(tmp_path, extractor)

        async def consume():
            async for _ in extraction.stream(make_job()):
                pass

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.2)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert downloader.released == 1
