"""
Unit tests for PdfExtractor.

Each test builds a small real PDF in tmp_path with pymupdf, so the extractor
runs against genuine PDF data.

Error tests assert only the HTTP status code of the raised ApiException.
"""

import logging

import pymupdf
import pytest

from src.exceptions.base import ApiException
from src.rag.services.extract.extractors.pdf_extractor import PdfExtractor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_pdf(tmp_path, pages, name="doc.pdf", **save_kwargs):
    """Build a PDF with one page per entry. An empty string makes a blank page."""
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    path = tmp_path / name
    document.save(path, **save_kwargs)
    document.close()
    return path


def extract(path):
    return list(PdfExtractor().extract(path))


# ---------------------------------------------------------------------------
# Core behavior
# ---------------------------------------------------------------------------


class TestCoreBehavior:

    def test_each_page_becomes_one_segment_with_its_page_number(self, tmp_path):
        path = make_pdf(tmp_path, ["Page one.", "Page two."])

        segments = extract(path)

        assert [(s.text, s.page) for s in segments] == [
            ("Page one.", 1),
            ("Page two.", 2),
        ]
        assert all(s.separator == "\n\n" for s in segments)

    def test_blank_pages_are_skipped_but_page_numbers_stay_true(self, tmp_path):
        path = make_pdf(tmp_path, ["First.", "", "Third."])

        assert [(s.text, s.page) for s in extract(path)] == [
            ("First.", 1),
            ("Third.", 3),
        ]

    def test_non_ascii_text_is_preserved(self, tmp_path):
        path = make_pdf(tmp_path, ["Café résumé"])

        assert extract(path)[0].text == "Café résumé"

    def test_nul_characters_are_removed_from_page_text(self, tmp_path):
        path = make_pdf(tmp_path, ["a\x00b"])

        assert extract(path)[0].text == "ab"

    def test_extract_is_lazy_and_yields_pages_one_at_a_time(self, tmp_path):
        path = make_pdf(tmp_path, ["One.", "Two."])

        iterator = PdfExtractor().extract(path)

        assert next(iterator).page == 1
        assert next(iterator).page == 2
        with pytest.raises(StopIteration):
            next(iterator)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:

    def test_file_that_is_not_a_pdf_raises_422(self, tmp_path):
        path = tmp_path / "fake.pdf"
        path.write_bytes(b"not a pdf at all")

        with pytest.raises(ApiException) as exc_info:
            extract(path)

        assert exc_info.value.status_code == 422

    def test_missing_file_raises_422(self, tmp_path):
        with pytest.raises(ApiException) as exc_info:
            extract(tmp_path / "missing.pdf")

        assert exc_info.value.status_code == 422

    def test_password_protected_pdf_raises_422_before_any_segment(self, tmp_path):
        path = make_pdf(
            tmp_path,
            ["secret"],
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw="user",
            owner_pw="owner",
        )
        iterator = PdfExtractor().extract(path)

        with pytest.raises(ApiException) as exc_info:
            next(iterator)

        assert exc_info.value.status_code == 422

    def test_pdf_with_only_blank_pages_raises_422(self, tmp_path):
        path = make_pdf(tmp_path, ["", ""])

        with pytest.raises(ApiException) as exc_info:
            extract(path)

        assert exc_info.value.status_code == 422

    def test_a_page_that_fails_is_skipped_and_the_others_are_kept(
        self, tmp_path, monkeypatch, caplog
    ):
        path = make_pdf(tmp_path, ["One.", "Two.", "Three."])
        original = pymupdf.Page.get_text

        def flaky(self, *args, **kwargs):
            if self.number == 1:
                raise RuntimeError("page failed")
            return original(self, *args, **kwargs)

        monkeypatch.setattr(pymupdf.Page, "get_text", flaky)

        with caplog.at_level(logging.WARNING):
            segments = extract(path)

        assert [(s.text, s.page) for s in segments] == [("One.", 1), ("Three.", 3)]
        assert any("Skipping page 2" in r.getMessage() for r in caplog.records)

    def test_pdf_where_every_page_fails_raises_422(self, tmp_path, monkeypatch):
        path = make_pdf(tmp_path, ["One.", "Two."])

        def always_fails(self, *args, **kwargs):
            raise RuntimeError("page failed")

        monkeypatch.setattr(pymupdf.Page, "get_text", always_fails)

        with pytest.raises(ApiException) as exc_info:
            extract(path)

        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# Damaged files
# ---------------------------------------------------------------------------


class TestDamagedFiles:

    def test_truncated_pdf_logs_a_repair_warning_and_keeps_readable_pages(
        self, tmp_path, caplog
    ):
        source = make_pdf(tmp_path, ["Page one.", "", "Page three."])
        raw = source.read_bytes()
        damaged = tmp_path / "damaged.pdf"
        damaged.write_bytes(raw[: len(raw) // 2])

        with caplog.at_level(logging.WARNING):
            segments = extract(damaged)

        assert [s.page for s in segments] == [1]
        assert any("repaired" in r.getMessage() for r in caplog.records)

    def test_intact_pdf_logs_no_repair_warning(self, tmp_path, caplog):
        path = make_pdf(tmp_path, ["Page one."])

        with caplog.at_level(logging.WARNING):
            extract(path)

        assert not any("repaired" in r.getMessage() for r in caplog.records)
