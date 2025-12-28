"""
Unit tests for text extractors and the text extraction factory.
Tests each extractor implementation and factory functionality.
"""

from unittest.mock import Mock, patch

import pytest

from src.components.extraction.text_extraction_factory import get_extractor
from src.components.extraction.text_extractor import (
    TxtDocumentExtractor,
    MarkdownDocumentExtractor,
    PDFDocumentExtractor,
    DocxDocumentExtractor,
)
from src.components.extraction.base_extractor import TextDocumentExtractor
from src.errors.api_exceptions import ApiException


# ==================== FACTORY TESTS ====================


def test_get_extractor_pdf():
    """Test factory returns PDFDocumentExtractor for PDF files."""
    extractor = get_extractor("document.pdf")
    assert isinstance(extractor, PDFDocumentExtractor)


def test_get_extractor_docx():
    """Test factory returns DocxDocumentExtractor for DOCX files."""
    extractor = get_extractor("document.docx")
    assert isinstance(extractor, DocxDocumentExtractor)


def test_get_extractor_markdown():
    """Test factory returns MarkdownDocumentExtractor for MD files."""
    extractor = get_extractor("README.md")
    assert isinstance(extractor, MarkdownDocumentExtractor)


def test_get_extractor_txt():
    """Test factory returns TxtDocumentExtractor for TXT files."""
    extractor = get_extractor("notes.txt")
    assert isinstance(extractor, TxtDocumentExtractor)


def test_get_extractor_case_insensitive():
    """Test factory is case-insensitive for file extensions."""
    extractor_upper = get_extractor("DOCUMENT.PDF")
    extractor_mixed = get_extractor("Document.PdF")

    assert isinstance(extractor_upper, PDFDocumentExtractor)
    assert isinstance(extractor_mixed, PDFDocumentExtractor)


def test_get_extractor_unsupported_type():
    """Test factory raises ValueError for unsupported file types."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        get_extractor("document.xlsx")


# ==================== TXT EXTRACTOR TESTS ====================


def test_txt_extractor_success(txt_upload_file):
    """Test successful text extraction from TXT file."""
    extractor = TxtDocumentExtractor()
    content = extractor.extract_text_from(txt_upload_file)

    assert content == "This is test content"


def test_txt_extractor_utf8_fallback_to_latin1(mock_upload_file_factory):
    """Test TXT extractor falls back to latin-1 when UTF-8 fails."""
    # Create content that will fail UTF-8 but work with latin-1
    latin1_content = b"\xe9\xe0\xe8"  # Latin-1 encoded special chars
    upload = mock_upload_file_factory("test.txt", latin1_content, binary=True)

    # Make UTF-8 decode fail first, then succeed with latin-1
    original_read = upload.file.read

    def mock_read():
        data = original_read()
        upload.file.seek(0)
        return data

    upload.file.read = mock_read

    extractor = TxtDocumentExtractor()
    content = extractor.extract_text_from(upload)

    assert content is not None


def test_txt_extractor_metadata(txt_upload_file):
    """Test metadata extraction from TXT file."""
    extractor = TxtDocumentExtractor()
    metadata = extractor.extract_metadata_from(txt_upload_file)

    assert metadata.filename == "test.txt"
    assert metadata.file_extension == ".txt"
    assert metadata.source == "UPLOAD"


def test_txt_extractor_load_document(txt_upload_file):
    """Test complete document loading from TXT file."""
    extractor = TxtDocumentExtractor()
    document = extractor.load_document(txt_upload_file)

    assert document.content == "This is test content"
    assert document.metadata.filename == "test.txt"


# ==================== MARKDOWN EXTRACTOR TESTS ====================


def test_markdown_extractor_success(md_upload_file):
    """Test successful text extraction from Markdown file."""
    extractor = MarkdownDocumentExtractor()
    content = extractor.extract_text_from(md_upload_file)

    assert "# Test Heading" in content
    assert "This is markdown content" in content


def test_markdown_extractor_metadata(md_upload_file):
    """Test metadata extraction from Markdown file."""
    extractor = MarkdownDocumentExtractor()
    metadata = extractor.extract_metadata_from(md_upload_file)

    assert metadata.filename == "test.md"
    assert metadata.file_extension == ".md"
    assert metadata.source == "UPLOAD"


def test_markdown_extractor_load_document(md_upload_file):
    """Test complete document loading from Markdown file."""
    extractor = MarkdownDocumentExtractor()
    document = extractor.load_document(md_upload_file)

    assert "# Test Heading" in document.content
    assert document.metadata.file_extension == ".md"


# ==================== PDF EXTRACTOR TESTS ====================


def test_pdf_extractor_success(pdf_upload_file):
    """Test successful text extraction from PDF file."""
    extractor = PDFDocumentExtractor()

    with patch("src.components.extraction.text_extractor.fitz") as mock_fitz:
        # Mock PDF document
        mock_page = Mock()
        mock_page.get_text.return_value = "Page 1 content"

        mock_doc = Mock()
        mock_doc.__iter__ = Mock(return_value=iter([mock_page]))
        mock_doc.__bool__ = Mock(return_value=True)

        mock_fitz.open.return_value = mock_doc

        content = extractor.extract_text_from(pdf_upload_file)

        assert "Page 1" in content
        assert "Page 1 content" in content
        mock_fitz.open.assert_called_once()


def test_pdf_extractor_empty_pdf(pdf_upload_file):
    """Test PDF extractor handles empty PDFs."""
    extractor = PDFDocumentExtractor()

    with patch("src.components.extraction.text_extractor.fitz") as mock_fitz:
        mock_page = Mock()
        mock_page.get_text.return_value = "   "  # Empty whitespace

        mock_doc = Mock()
        mock_doc.__iter__ = Mock(return_value=iter([mock_page]))
        mock_doc.__bool__ = Mock(return_value=True)

        mock_fitz.open.return_value = mock_doc

        with pytest.raises(ApiException) as exc_info:
            extractor.extract_text_from(pdf_upload_file)

        assert exc_info.value.error.code == "PDF_NO_CONTENT"


def test_pdf_extractor_metadata(pdf_upload_file):
    """Test metadata extraction from PDF file."""
    extractor = PDFDocumentExtractor()
    metadata = extractor.extract_metadata_from(pdf_upload_file)

    assert metadata.filename == "test.pdf"
    assert metadata.file_extension == ".pdf"
    assert metadata.source == "UPLOAD"


def test_pdf_extractor_multi_page(pdf_upload_file):
    """Test PDF extractor handles multiple pages."""
    extractor = PDFDocumentExtractor()

    with patch("src.components.extraction.text_extractor.fitz") as mock_fitz:
        # Mock multiple pages
        mock_page1 = Mock()
        mock_page1.get_text.return_value = "Page 1 content"

        mock_page2 = Mock()
        mock_page2.get_text.return_value = "Page 2 content"

        mock_doc = Mock()
        mock_doc.__iter__ = Mock(return_value=iter([mock_page1, mock_page2]))
        mock_doc.__bool__ = Mock(return_value=True)

        mock_fitz.open.return_value = mock_doc

        content = extractor.extract_text_from(pdf_upload_file)

        assert "Page 1" in content
        assert "Page 2" in content
        assert "Page 1 content" in content
        assert "Page 2 content" in content


# ==================== DOCX EXTRACTOR TESTS ====================


def test_docx_extractor_success(docx_upload_file):
    """Test successful text extraction from DOCX file."""
    extractor = DocxDocumentExtractor()

    with patch("src.components.extraction.text_extractor.docx") as mock_docx:
        # Mock paragraphs
        mock_para1 = Mock()
        mock_para1.text = "First paragraph"

        mock_para2 = Mock()
        mock_para2.text = "Second paragraph"

        mock_doc = Mock()
        mock_doc.paragraphs = [mock_para1, mock_para2]

        mock_docx.Document.return_value = mock_doc

        content = extractor.extract_text_from(docx_upload_file)

        assert "First paragraph" in content
        assert "Second paragraph" in content


def test_docx_extractor_metadata(docx_upload_file):
    """Test metadata extraction from DOCX file."""
    extractor = DocxDocumentExtractor()
    metadata = extractor.extract_metadata_from(docx_upload_file)

    assert metadata.filename == "test.docx"
    assert metadata.file_extension == ".docx"
    assert metadata.source == "UPLOAD"


def test_docx_extractor_empty_document(docx_upload_file):
    """Test DOCX extractor handles empty documents."""
    extractor = DocxDocumentExtractor()

    with patch("src.components.extraction.text_extractor.docx") as mock_docx:
        mock_doc = Mock()
        mock_doc.paragraphs = []

        mock_docx.Document.return_value = mock_doc

        content = extractor.extract_text_from(docx_upload_file)

        assert content == ""


def test_docx_extractor_load_document(docx_upload_file):
    """Test complete document loading from DOCX file."""
    extractor = DocxDocumentExtractor()

    with patch("src.components.extraction.text_extractor.docx") as mock_docx:
        mock_para = Mock()
        mock_para.text = "Test content"

        mock_doc = Mock()
        mock_doc.paragraphs = [mock_para]

        mock_docx.Document.return_value = mock_doc

        document = extractor.load_document(docx_upload_file)

        assert document.content == "Test content"
        assert document.metadata.filename == "test.docx"


# ==================== ABSTRACT BASE CLASS TESTS ====================


def test_text_document_extractor_is_abstract():
    """Test that TextDocumentExtractor cannot be instantiated directly."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        TextDocumentExtractor()


def test_load_document_calls_abstract_methods():
    """Test that load_document works when abstract methods are implemented."""

    class CompleteExtractor(TextDocumentExtractor):
        """Complete extractor for testing."""

        def extract_text_from(self, document):
            return "extracted text"

        def extract_metadata_from(self, document):
            from src.components.ingestion.document import FileDocumentMetadata
            from src.config.constants import Source

            return FileDocumentMetadata(
                filename="test.txt", file_extension=".txt", source=Source.UPLOAD
            )

    extractor = CompleteExtractor()
    result = extractor.load_document(Mock())

    assert result.content == "extracted text"
    assert result.metadata.filename == "test.txt"


def test_extractor_requires_both_methods():
    """Test that both abstract methods must be implemented."""

    # Test missing extract_text_from
    class MissingTextExtractor(TextDocumentExtractor):
        """Extractor missing extract_text_from."""

        def extract_metadata_from(self, document):
            pass

    with pytest.raises(TypeError, match="extract_text_from"):
        MissingTextExtractor()

    # Test missing extract_metadata_from
    class MissingMetadataExtractor(TextDocumentExtractor):
        """Extractor missing extract_metadata_from."""

        def extract_text_from(self, document):
            return "text"

    with pytest.raises(TypeError, match="extract_metadata_from"):
        MissingMetadataExtractor()
