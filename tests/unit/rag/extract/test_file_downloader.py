"""
Unit tests for S3FileDownloader.

The object storage is replaced with a mock that writes bytes to the path the
downloader gives it. Temporary directories are redirected into pytest's
tmp_path, so every test checks for leftover files or directories by listing
that folder.

Error tests assert only the HTTP status code of the raised ApiException.
"""

import asyncio
import hashlib
import tempfile
import threading
from unittest.mock import MagicMock

import pytest

from src.exceptions import not_found_error
from src.exceptions.base import ApiException
from src.rag.services.extract.file_downloader import S3FileDownloader
from src.uploads.storage.object_storage import ObjectStorage

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

DATA = b"hello world"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(autouse=True)
def isolated_tmp(tmp_path, monkeypatch):
    """Put every temporary directory the downloader creates inside tmp_path."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path


def make_storage(data: bytes = DATA, *, error=None, write: bool = True) -> MagicMock:
    """
    A mock ObjectStorage. download_to raises `error` when given, otherwise
    writes `data` to the target path, unless `write` is False.
    """
    storage = MagicMock(spec=ObjectStorage)

    def download_to(key, path):
        if error is not None:
            raise error
        if write:
            path.write_bytes(data)

    storage.download_to.side_effect = download_to
    return storage


# ---------------------------------------------------------------------------
# Core behavior
# ---------------------------------------------------------------------------


class TestCoreBehavior:

    @pytest.mark.asyncio
    async def test_yields_a_path_to_the_downloaded_file(self):
        downloader = S3FileDownloader(make_storage())

        async with downloader.download("docs/a.pdf", sha256(DATA), ".pdf") as path:
            assert path.is_file()
            assert path.read_bytes() == DATA

    @pytest.mark.asyncio
    async def test_downloads_the_requested_key_to_the_yielded_path(self):
        storage = make_storage()
        downloader = S3FileDownloader(storage)

        async with downloader.download("docs/a.pdf", sha256(DATA), ".pdf") as path:
            pass

        storage.download_to.assert_called_once_with("docs/a.pdf", path)

    @pytest.mark.asyncio
    async def test_suffix_is_normalized_into_the_file_name(self):
        cases = {
            ".pdf": "download.pdf",
            "pdf": "download.pdf",
            " .txt ": "download.txt",
            ".tar.gz": "download.tar.gz",
            "": "download",
        }

        for suffix, expected_name in cases.items():
            downloader = S3FileDownloader(make_storage())

            async with downloader.download("k", sha256(DATA), suffix) as path:
                assert path.name == expected_name

    @pytest.mark.asyncio
    async def test_expected_checksum_ignores_case_and_surrounding_whitespace(self):
        for expected in (sha256(DATA).upper(), f"  {sha256(DATA)}\n"):
            downloader = S3FileDownloader(make_storage())

            async with downloader.download("k", expected, ".txt") as path:
                assert path.read_bytes() == DATA

    @pytest.mark.asyncio
    async def test_empty_file_is_downloaded_and_verified(self):
        downloader = S3FileDownloader(make_storage(b""))

        async with downloader.download("k", sha256(b""), ".txt") as path:
            assert path.read_bytes() == b""

    @pytest.mark.asyncio
    async def test_large_binary_file_checksum_is_verified(self):
        # About 5 MB, larger than any single read the hashing code makes.
        data = bytes(range(256)) * 20_000
        downloader = S3FileDownloader(make_storage(data))

        async with downloader.download("k", sha256(data), ".bin") as path:
            assert path.stat().st_size == len(data)

    @pytest.mark.asyncio
    async def test_download_runs_off_the_event_loop_thread(self):
        storage = MagicMock(spec=ObjectStorage)
        threads: list[threading.Thread] = []

        def download_to(key, path):
            threads.append(threading.current_thread())
            path.write_bytes(DATA)

        storage.download_to.side_effect = download_to
        downloader = S3FileDownloader(storage)

        async with downloader.download("k", sha256(DATA), ".txt"):
            pass

        assert len(threads) == 1
        assert threads[0] is not threading.current_thread()

    @pytest.mark.asyncio
    async def test_concurrent_downloads_use_separate_directories(self):
        objects = {"a": b"AAA", "b": b"BBB"}
        storage = MagicMock(spec=ObjectStorage)
        storage.download_to.side_effect = lambda key, path: path.write_bytes(
            objects[key]
        )
        downloader = S3FileDownloader(storage)

        async def fetch(key):
            async with downloader.download(key, sha256(objects[key]), ".txt") as path:
                await asyncio.sleep(0.01)
                return path.parent, path.read_bytes()

        (dir_a, content_a), (dir_b, content_b) = await asyncio.gather(
            fetch("a"), fetch("b")
        )

        assert content_a == b"AAA"
        assert content_b == b"BBB"
        assert dir_a != dir_b


# ---------------------------------------------------------------------------
# Temporary directory cleanup
# ---------------------------------------------------------------------------


class TestCleanup:

    @pytest.mark.asyncio
    async def test_temp_directory_is_removed_when_the_context_exits(self, isolated_tmp):
        downloader = S3FileDownloader(make_storage())

        async with downloader.download("k", sha256(DATA), ".txt") as path:
            assert path.exists()
            assert list(isolated_tmp.iterdir()) == [path.parent]

        assert not path.exists()
        assert list(isolated_tmp.iterdir()) == []

    @pytest.mark.asyncio
    async def test_temp_directory_is_removed_when_the_caller_raises(self, isolated_tmp):
        downloader = S3FileDownloader(make_storage())

        with pytest.raises(ValueError):
            async with downloader.download("k", sha256(DATA), ".txt"):
                raise ValueError("processing failed")

        assert list(isolated_tmp.iterdir()) == []

    @pytest.mark.asyncio
    async def test_temp_directory_is_removed_after_a_download_failure(
        self, isolated_tmp
    ):
        failing_downloaders = (
            S3FileDownloader(make_storage()),  # checksum mismatch below
            S3FileDownloader(make_storage(error=RuntimeError("boom"))),
            S3FileDownloader(make_storage(write=False)),
        )

        for downloader in failing_downloaders:
            with pytest.raises(ApiException):
                async with downloader.download("k", "0" * 64, ".txt"):
                    pass

            assert list(isolated_tmp.iterdir()) == []


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:

    @pytest.mark.asyncio
    async def test_checksum_mismatch_raises_409_before_the_body_runs(self):
        downloader = S3FileDownloader(make_storage())
        body_ran = False

        with pytest.raises(ApiException) as exc_info:
            async with downloader.download("k", sha256(b"other"), ".txt"):
                body_ran = True

        assert exc_info.value.status_code == 409
        assert body_ran is False

    @pytest.mark.asyncio
    async def test_malformed_expected_checksum_raises_409(self):
        for expected in ("", "not-a-checksum", "0" * 64):
            downloader = S3FileDownloader(make_storage())

            with pytest.raises(ApiException) as exc_info:
                async with downloader.download("k", expected, ".txt"):
                    pass

            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_unexpected_storage_error_raises_500_with_the_cause_chained(self):
        boom = RuntimeError("boom")
        downloader = S3FileDownloader(make_storage(error=boom))

        with pytest.raises(ApiException) as exc_info:
            async with downloader.download("k", sha256(DATA), ".txt"):
                pass

        assert exc_info.value.status_code == 500
        assert exc_info.value.__cause__ is boom

    @pytest.mark.asyncio
    async def test_api_exception_from_storage_passes_through_unchanged(self):
        original = not_found_error("missing")
        downloader = S3FileDownloader(make_storage(error=original))

        with pytest.raises(ApiException) as exc_info:
            async with downloader.download("k", sha256(DATA), ".txt"):
                pass

        assert exc_info.value is original
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_storage_that_writes_no_file_raises_500(self):
        downloader = S3FileDownloader(make_storage(write=False))

        with pytest.raises(ApiException) as exc_info:
            async with downloader.download("k", sha256(DATA), ".txt"):
                pass

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_unsafe_suffix_raises_422_and_creates_nothing(self, isolated_tmp):
        unsafe_suffixes = (
            "/../../escape_marker",
            "a/b",
            "pdf/",
            "..\\x",
            ".p\x00df",
            ".",
            "x" * 40,
        )

        for suffix in unsafe_suffixes:
            storage = make_storage()
            downloader = S3FileDownloader(storage)

            with pytest.raises(ApiException) as exc_info:
                async with downloader.download("k", sha256(DATA), suffix):
                    pass

            assert exc_info.value.status_code == 422
            storage.download_to.assert_not_called()
            assert list(isolated_tmp.iterdir()) == []
