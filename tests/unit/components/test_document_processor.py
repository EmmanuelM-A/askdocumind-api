"""
Unit tests for the DocumentProcessor class.

Tests cover:
- Core functionality (processing single/multiple files)
- Edge cases (empty files, invalid content, unsupported types)
- Memory efficiency (streaming behavior)
- Error handling and validation
"""

from unittest.mock import Mock, patch
import pytest

from src.components.ingestion.document import FileDocument, FileDocumentMetadata
from src.errors.api_exceptions import ApiException

# ========================================
# Core Functionality Tests
# ========================================


def test_processor_initialization(processor):
    """Test that DocumentProcessor initializes correctly with text splitter."""
    assert processor is not None
    assert processor.splitter is not None
    assert processor.splitter._chunk_size > 0
    assert processor.splitter._chunk_overlap >= 0


@patch("src.components.ingestion.document_processor.get_extractor")
@patch("src.components.ingestion.document_processor.validate_document_content")
def test_process_single_valid_file(
    mock_validate, mock_get_extractor, processor, mock_upload_file, mock_document
):
    """Test processing a single valid file produces chunks."""
    # Arrange
    content = "This is a test document. " * 100  # Long enough to potentially chunk
    upload = mock_upload_file("test.pdf", content)

    mock_extractor = Mock()
    mock_extractor.load_document.return_value = mock_document(content, "test.pdf")
    mock_get_extractor.return_value = mock_extractor
    mock_validate.return_value = (True, content)

    # Act
    chunks = list(processor.process([upload]))

    # Assert
    assert len(chunks) > 0
    assert all(isinstance(chunk, FileDocument) for chunk in chunks)
    assert all(chunk.content.strip() for chunk in chunks)
    mock_get_extractor.assert_called_once_with("test.pdf")
    mock_extractor.load_document.assert_called_once()


@patch("src.components.ingestion.document_processor.get_extractor")
@patch("src.components.ingestion.document_processor.validate_document_content")
def test_process_multiple_valid_files(
    mock_validate, mock_get_extractor, processor, mock_upload_file, mock_document
):
    """Test processing multiple valid files produces chunks from all files."""
    # Arrange
    content1 = "First document content. " * 50
    content2 = "Second document content. " * 50
    upload1 = mock_upload_file("doc1.txt", content1)
    upload2 = mock_upload_file("doc2.pdf", content2)

    mock_extractor = Mock()
    mock_extractor.load_document.side_effect = [
        mock_document(content1, "doc1.txt"),
        mock_document(content2, "doc2.pdf"),
    ]
    mock_get_extractor.return_value = mock_extractor
    mock_validate.side_effect = [(True, content1), (True, content2)]

    # Act
    chunks = list(processor.process([upload1, upload2]))

    # Assert
    assert len(chunks) > 0
    assert mock_get_extractor.call_count == 2
    assert mock_extractor.load_document.call_count == 2


@patch("src.components.ingestion.document_processor.get_extractor")
@patch("src.components.ingestion.document_processor.validate_document_content")
def test_process_yields_chunks_incrementally(
    mock_validate, mock_get_extractor, processor, mock_upload_file, mock_document
):
    """Test that process() yields chunks as a generator (streaming behavior)."""
    # Arrange
    content = "Test content. " * 100
    upload = mock_upload_file("test.txt", content)

    mock_extractor = Mock()
    mock_extractor.load_document.return_value = mock_document(content, "test.txt")
    mock_get_extractor.return_value = mock_extractor
    mock_validate.return_value = (True, content)

    # Act
    result = processor.process([upload])

    # Assert - result should be a generator
    assert hasattr(result, "__iter__")
    assert hasattr(result, "__next__")

    # Consume one chunk to verify it works
    first_chunk = next(result)
    assert isinstance(first_chunk, FileDocument)


# ========================================
# Edge Cases and Error Handling
# ========================================


def test_process_empty_file_list_raises_error(processor):
    """Test that processing an empty file list raises ApiException."""
    with pytest.raises(ApiException) as exc_info:
        list(processor.process([]))

    assert "No files provided" in str(exc_info.value)


@patch("src.components.ingestion.document_processor.get_extractor")
def test_process_unsupported_file_type_skips_file(
    mock_get_extractor, processor, mock_upload_file
):
    """Test that unsupported file types are skipped gracefully."""
    # Arrange
    upload = mock_upload_file("test.unsupported", "content")
    mock_get_extractor.side_effect = ValueError("Unsupported file type")

    # Act & Assert - should raise since no valid chunks produced
    with pytest.raises(ApiException) as exc_info:
        list(processor.process([upload]))

    assert "No valid document chunks" in str(exc_info.value)


@patch("src.components.ingestion.document_processor.get_extractor")
@patch("src.components.ingestion.document_processor.validate_document_content")
def test_process_extraction_failure_skips_file(
    mock_validate, mock_get_extractor, processor, mock_upload_file
):
    """Test that files that fail extraction are skipped."""
    # Arrange
    upload = mock_upload_file("test.pdf", "content")

    mock_extractor = Mock()
    mock_extractor.load_document.side_effect = Exception("Extraction failed")
    mock_get_extractor.return_value = mock_extractor

    # Act & Assert
    with pytest.raises(ApiException) as exc_info:
        list(processor.process([upload]))

    assert "No valid document chunks" in str(exc_info.value)


@patch("src.components.ingestion.document_processor.get_extractor")
@patch("src.components.ingestion.document_processor.validate_document_content")
def test_process_validation_failure_skips_file(
    mock_validate, mock_get_extractor, processor, mock_upload_file, mock_document
):
    """Test that files that fail validation are skipped."""
    # Arrange
    content = "Test content"
    upload = mock_upload_file("test.txt", content)

    mock_extractor = Mock()
    mock_extractor.load_document.return_value = mock_document(content, "test.txt")
    mock_get_extractor.return_value = mock_extractor
    mock_validate.return_value = (False, None)  # Validation fails

    # Act & Assert
    with pytest.raises(ApiException) as exc_info:
        list(processor.process([upload]))

    assert "No valid document chunks" in str(exc_info.value)


@patch("src.components.ingestion.document_processor.get_extractor")
@patch("src.components.ingestion.document_processor.validate_document_content")
def test_process_empty_content_after_validation_skips_file(
    mock_validate, mock_get_extractor, processor, mock_upload_file, mock_document
):
    """Test that files with empty content after validation are skipped."""
    # Arrange
    content = "Test content"
    upload = mock_upload_file("test.txt", content)

    mock_extractor = Mock()
    mock_extractor.load_document.return_value = mock_document(content, "test.txt")
    mock_get_extractor.return_value = mock_extractor
    mock_validate.return_value = (True, "")  # Empty cleaned content

    # Act & Assert
    with pytest.raises(ApiException) as exc_info:
        list(processor.process([upload]))

    assert "No valid document chunks" in str(exc_info.value)


@patch("src.components.ingestion.document_processor.get_extractor")
@patch("src.components.ingestion.document_processor.validate_document_content")
def test_process_mixed_valid_and_invalid_files(
    mock_validate, mock_get_extractor, processor, mock_upload_file, mock_document
):
    """Test processing mixed valid and invalid files only yields chunks from valid files."""
    # Arrange
    valid_content = "Valid document content. " * 50
    invalid_content = "Invalid"

    upload1 = mock_upload_file("valid.txt", valid_content)
    upload2 = mock_upload_file("invalid.txt", invalid_content)

    mock_extractor = Mock()
    mock_extractor.load_document.side_effect = [
        mock_document(valid_content, "valid.txt"),
        mock_document(invalid_content, "invalid.txt"),
    ]
    mock_get_extractor.return_value = mock_extractor
    mock_validate.side_effect = [
        (True, valid_content),  # First file valid
        (False, None),  # Second file invalid
    ]

    # Act
    chunks = list(processor.process([upload1, upload2]))

    # Assert - should have chunks only from valid file
    assert len(chunks) > 0
    assert all(isinstance(chunk, FileDocument) for chunk in chunks)


@patch("src.components.ingestion.document_processor.get_extractor")
@patch("src.components.ingestion.document_processor.validate_document_content")
def test_process_filters_empty_chunks(
    mock_validate, mock_get_extractor, processor, mock_upload_file, mock_document
):
    """Test that empty or whitespace-only chunks are filtered out."""
    # Arrange
    content = "Valid content for testing"
    upload = mock_upload_file("test.txt", content)

    mock_extractor = Mock()
    mock_extractor.load_document.return_value = mock_document(content, "test.txt")
    mock_get_extractor.return_value = mock_extractor
    mock_validate.return_value = (True, content)

    # Mock splitter to return some empty chunks
    with patch.object(
        processor.splitter,
        "split_text",
        return_value=["Valid chunk", "   ", "", "Another valid chunk"],
    ):
        # Act
        chunks = list(processor.process([upload]))

    # Assert - empty chunks should be filtered
    assert len(chunks) == 2
    assert all(chunk.content.strip() for chunk in chunks)


@patch("src.components.ingestion.document_processor.get_extractor")
@patch("src.components.ingestion.document_processor.validate_document_content")
def test_process_preserves_metadata_in_chunks(
    mock_validate, mock_get_extractor, processor, mock_upload_file
):
    """Test that document metadata is preserved in all chunks."""
    # Arrange
    content = "Test content. " * 100
    upload = mock_upload_file("important.pdf", content)

    original_metadata = FileDocumentMetadata(
        filename="important.pdf",
        file_extension=".pdf",
        author="Test Author",
        document_id="doc-123",
    )

    mock_doc = FileDocument(content=content, metadata=original_metadata)

    mock_extractor = Mock()
    mock_extractor.load_document.return_value = mock_doc
    mock_get_extractor.return_value = mock_extractor
    mock_validate.return_value = (True, content)

    # Act
    chunks = list(processor.process([upload]))

    # Assert
    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk.metadata.filename == "important.pdf"
        assert chunk.metadata.file_extension == ".pdf"
        assert chunk.metadata.author == "Test Author"
        assert chunk.metadata.document_id == "doc-123"
