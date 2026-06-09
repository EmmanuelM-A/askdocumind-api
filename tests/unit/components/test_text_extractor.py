"""
Unit tests for text extractors and the text extraction factory.
Tests each extractor implementation and factory functionality.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from src.components.extraction.text_extraction_factory import get_text_extractor
from src.components.extraction.text_extractor import (
    DocxDocumentExtractor,
    MarkdownDocumentExtractor,
    PDFDocumentExtractor,
    TextDocumentExtractor,
    TxtDocumentExtractor,
)
from src.errors.api_exceptions import ApiException

# ==================== FACTORY TESTS ====================


@pytest.mark.parametrize(
    ("filename", "expected_type"),
    [
        ("document.pdf", PDFDocumentExtractor),
        ("document.docx", DocxDocumentExtractor),
        ("README.md", MarkdownDocumentExtractor),
        ("notes.txt", TxtDocumentExtractor),
        ("ARCHIVE.BACKUP.PDF", PDFDocumentExtractor),
        ("report.final.MD", MarkdownDocumentExtractor),
        ("Document.TxT", TxtDocumentExtractor),
    ],
)
def test_get_extractor_by_extension(filename, expected_type):
    """Test factory returns the correct extractor for supported file types."""
    extractor = get_text_extractor(filename)
    assert isinstance(extractor, expected_type)


def test_get_extractor_unsupported_type():
    """Test factory raises ValueError for unsupported file types."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        get_text_extractor("document.xlsx")


def test_get_extractor_missing_extension():
    """Test factory raises ValueError when no file extension is present."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        get_text_extractor("document")


# ==================== TXT EXTRACTOR TESTS ====================


def test_txt_extractor_success():
    """Test successful text extraction from TXT bytes."""
    extractor = TxtDocumentExtractor()
    content = extractor.extract_text_from(b"This is test content", "test.txt")

    assert content == "This is test content"


def test_txt_extractor_utf8_fallback_to_latin1():
    """Test TXT extractor falls back to latin-1 when UTF-8 fails."""
    extractor = TxtDocumentExtractor()
    content = extractor.extract_text_from(b"\xe9\xe0\xe8", "test.txt")

    assert content == "éàè"


# ==================== MARKDOWN EXTRACTOR TESTS ====================


def test_markdown_extractor_success():
    """Test successful text extraction from Markdown bytes."""
    extractor = MarkdownDocumentExtractor()
    content = extractor.extract_text_from(
        b"# Test Heading\n\nThis is markdown content",
        "test.md",
    )

    assert "# Test Heading" in content
    assert "This is markdown content" in content


# ==================== PDF EXTRACTOR TESTS ====================


def test_pdf_extractor_success():
    """Test successful text extraction from PDF bytes."""
    extractor = PDFDocumentExtractor()
    pdf_bytes = b"%PDF-1.4 mock content"

    with patch("src.components.extraction.text_extractor.pymupdf") as mock_pymupdf:
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Page 1 content"

        mock_doc = MagicMock()
        mock_doc.__iter__.return_value = iter([mock_page])
        mock_doc.__bool__.return_value = True

        mock_pymupdf.open.return_value = mock_doc

        content = extractor.extract_text_from(pdf_bytes, "test.pdf")

        assert "Page 1" in content
        assert "Page 1 content" in content
    mock_pymupdf.open.assert_called_once_with(stream=pdf_bytes, filetype="pdf")


def test_pdf_extractor_empty_pdf_raises_error():
    """Test PDF extractor raises an error when no readable content is found."""
    extractor = PDFDocumentExtractor()
    pdf_bytes = b"%PDF-1.4 mock content"

    with patch("src.components.extraction.text_extractor.pymupdf") as mock_pymupdf:
        mock_page = MagicMock()
        mock_page.get_text.return_value = "   "

        mock_doc = MagicMock()
        mock_doc.__iter__.return_value = iter([mock_page])
        mock_doc.__bool__.return_value = True

        mock_pymupdf.open.return_value = mock_doc

        with pytest.raises(ApiException) as exc_info:
            extractor.extract_text_from(pdf_bytes, "test.pdf")

    assert exc_info.value.error.code == "PDF_NO_CONTENT"


def test_pdf_extractor_multi_page():
    """Test PDF extractor handles multiple pages."""
    extractor = PDFDocumentExtractor()
    pdf_bytes = b"%PDF-1.4 mock content"

    with patch("src.components.extraction.text_extractor.pymupdf") as mock_pymupdf:
        mock_page1 = MagicMock()
        mock_page1.get_text.return_value = "Page 1 content"

        mock_page2 = MagicMock()
        mock_page2.get_text.return_value = "Page 2 content"

        mock_doc = MagicMock()
        mock_doc.__iter__.return_value = iter([mock_page1, mock_page2])
        mock_doc.__bool__.return_value = True

        mock_pymupdf.open.return_value = mock_doc

        content = extractor.extract_text_from(pdf_bytes, "test.pdf")

        assert "Page 1" in content
        assert "Page 2" in content
        assert "Page 1 content" in content
        assert "Page 2 content" in content


# ==================== DOCX EXTRACTOR TESTS ====================


def test_docx_extractor_success():
    """Test successful text extraction from DOCX bytes."""
    extractor = DocxDocumentExtractor()
    docx_bytes = b"PK mock docx"

    with patch("src.components.extraction.text_extractor.docx") as mock_docx:
        mock_para1 = Mock()
        mock_para1.text = "First paragraph"

        mock_para2 = Mock()
        mock_para2.text = "Second paragraph"

        mock_doc = Mock()
        mock_doc.paragraphs = [mock_para1, mock_para2]

        mock_docx.Document.return_value = mock_doc

        content = extractor.extract_text_from(docx_bytes, "test.docx")

        assert "First paragraph" in content
        assert "Second paragraph" in content


def test_docx_extractor_missing_dependency_raises_error():
    """Test DOCX extractor raises an error when python-docx is unavailable."""
    extractor = DocxDocumentExtractor()

    with patch("src.components.extraction.text_extractor.docx", None):
        with pytest.raises(ApiException) as exc_info:
            extractor.extract_text_from(b"PK mock docx", "test.docx")

    assert exc_info.value.error.code == "MISSING_PYTHON_DOCX"


# ==================== ABSTRACT BASE CLASS TESTS ====================


def test_text_document_extractor_is_abstract():
    """Test that TextDocumentExtractor cannot be instantiated directly."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        TextDocumentExtractor()
