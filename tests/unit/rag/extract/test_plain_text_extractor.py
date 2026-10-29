"""
Unit tests for PlainTextExtractor.

Each test writes a small file to tmp_path. The two settings the extractor
reads are patched, and the charset detector is patched where a test needs a
fixed detection result.

Error tests assert only the HTTP status code of the raised ApiException.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.exceptions.base import ApiException
from src.rag.services.extract.extractors.plain_text_extractor import (
    PlainTextExtractor,
)

MODULE = "src.rag.services.extract.extractors.plain_text_extractor"

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def settings():
    """Patch the settings used by this module and by group_blocks."""
    fake = SimpleNamespace(
        rag=SimpleNamespace(
            READ_BLOCK_BYTES=65_536,
            FALLBACK_ENCODING="latin-1",
            SEGMENT_TARGET_CHARS=10_000,
        )
    )
    with patch(f"{MODULE}.settings", fake), patch(
        "src.rag.services.extract.extractors.extractor.settings", fake
    ):
        yield fake


def write(tmp_path, data: bytes, name="file.txt"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def extract(path):
    return list(PlainTextExtractor().extract(path))


def rebuild(segments) -> str:
    """Join segments the way Chunker.chunk_stream does."""
    text = ""
    for segment in segments:
        if text:
            text += segment.separator
        text += segment.text
    return text


def detector_returning(encoding):
    """A fake charset_normalizer.from_path whose best match is `encoding`."""
    best = SimpleNamespace(encoding=encoding) if encoding else None
    return lambda path: SimpleNamespace(best=lambda: best)


# ---------------------------------------------------------------------------
# Core behavior
# ---------------------------------------------------------------------------


class TestCoreBehavior:

    def test_text_becomes_one_segment_with_a_newline_separator(self, tmp_path):
        path = write(tmp_path, b"line one\nline two\nline three")

        segments = extract(path)

        assert len(segments) == 1
        assert segments[0].text == "line one\nline two\nline three"
        assert segments[0].page is None
        assert segments[0].separator == "\n"

    def test_crlf_and_lone_cr_line_endings_become_newlines(self, tmp_path):
        path = write(tmp_path, b"a\r\nb\rc\n")

        assert extract(path)[0].text == "a\nb\nc"

    def test_blank_lines_and_indentation_are_preserved(self, tmp_path):
        path = write(tmp_path, b"def f():\n\n    return 1\n")

        assert extract(path)[0].text == "def f():\n\n    return 1"

    def test_segments_split_at_the_target_size_and_rebuild_the_exact_text(
        self, tmp_path, settings
    ):
        settings.rag.SEGMENT_TARGET_CHARS = 100
        original = "line1\n\nline3\n  indented\n" * 50 + "end"
        path = write(tmp_path, original.encode())

        segments = extract(path)

        assert len(segments) > 1
        assert rebuild(segments) == original

    def test_empty_and_whitespace_only_files_yield_no_segments(self, tmp_path):
        assert extract(write(tmp_path, b"")) == []
        assert extract(write(tmp_path, b"\n  \n\t\n", "ws.txt")) == []

    def test_text_is_read_correctly_when_a_character_spans_a_read_block(
        self, tmp_path, settings
    ):
        settings.rag.READ_BLOCK_BYTES = 3
        path = write(tmp_path, "aéb€c🙂d".encode())

        assert extract(path)[0].text == "aéb€c🙂d"


# ---------------------------------------------------------------------------
# Encoding detection
# ---------------------------------------------------------------------------


class TestEncoding:

    def test_utf8_is_read_without_calling_the_detector(self, tmp_path):
        path = write(tmp_path, "héllo wörld 日本語".encode())

        with patch(f"{MODULE}.from_path", side_effect=AssertionError("not needed")):
            assert extract(path)[0].text == "héllo wörld 日本語"

    def test_utf8_bom_is_removed(self, tmp_path):
        path = write(tmp_path, b"\xef\xbb\xbfhello")

        assert extract(path)[0].text == "hello"

    def test_utf16_text_is_detected_and_decoded(self, tmp_path):
        path = write(tmp_path, "héllo\nwörld".encode("utf-16"))

        assert extract(path)[0].text == "héllo\nwörld"

    def test_non_utf8_file_uses_the_detected_encoding(self, tmp_path):
        path = write(tmp_path, "café".encode("cp1252"))

        with patch(f"{MODULE}.from_path", detector_returning("cp1252")):
            assert extract(path)[0].text == "café"

    def test_fallback_encoding_is_used_when_nothing_is_detected(self, tmp_path):
        path = write(tmp_path, b"caf\xe9")

        with patch(f"{MODULE}.from_path", detector_returning(None)):
            assert extract(path)[0].text == "café"

    def test_undecodable_bytes_become_replacement_characters(self, tmp_path):
        path = write(tmp_path, b"ok \xff end")

        with patch(f"{MODULE}.from_path", detector_returning("utf-8")):
            assert extract(path)[0].text == "ok � end"


# ---------------------------------------------------------------------------
# NUL characters and binary files
# ---------------------------------------------------------------------------


class TestBinaryAndNul:

    def test_a_stray_nul_in_a_larger_text_file_is_removed(self, tmp_path):
        data = b"a" * 500 + b"\x00" + b"b" * 500
        path = write(tmp_path, data)

        assert extract(path)[0].text == "a" * 500 + "b" * 500

    def test_binary_data_raises_422(self, tmp_path):
        path = write(tmp_path, b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 40)

        with pytest.raises(ApiException) as exc_info:
            extract(path)

        assert exc_info.value.status_code == 422

    def test_utf16_text_is_not_mistaken_for_binary(self, tmp_path):
        # UTF-16 stores plain ASCII as bytes alternating with NUL.
        path = write(tmp_path, ("plain ascii line\n" * 50).encode("utf-16"))

        assert extract(path)[0].text.startswith("plain ascii line")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:

    def test_missing_file_raises_422(self, tmp_path):
        with pytest.raises(ApiException) as exc_info:
            extract(tmp_path / "missing.txt")

        assert exc_info.value.status_code == 422

    def test_directory_instead_of_a_file_raises_422(self, tmp_path):
        with pytest.raises(ApiException) as exc_info:
            extract(tmp_path)

        assert exc_info.value.status_code == 422
