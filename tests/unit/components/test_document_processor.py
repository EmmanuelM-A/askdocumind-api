"""
Unit tests for the UploadedDocumentProcessor class.

Tests cover:
- Core functionality (processing single/multiple files)
- Edge cases (empty files, invalid content, unsupported types)
- Memory efficiency (streaming behavior)
- Error handling and validation
"""

from unittest.mock import Mock, patch
from uuid import uuid4

import pytest


# ========================================
# Core Functionality Tests
# ========================================


def test_processor_initialization(processor):
    """Test that UploadedDocumentProcessor initializes correctly with text splitter."""
    assert processor is not None
    assert processor.splitter is not None
    assert processor.splitter._chunk_size > 0
    assert processor.splitter._chunk_overlap >= 0


def test_process_single_valid_file(processor):
    """Test processing a single valid file produces streamed tuples with document_id and chunk."""
    content = "This is a test document. " * 100
    doc_id = uuid4()
    filename = "test.pdf"
    file_bytes = content.encode("utf-8")

    mock_extractor = Mock()
    mock_extractor.extract_text_from.return_value = content

    with patch(
        "src.components.ingestion.document_processor.get_text_extractor",
        return_value=mock_extractor,
    ) as mock_get_text_extractor, patch.object(
        processor,
        "_split_content",
        return_value=["chunk-1", "chunk-2"],
    ) as mock_split_content:
        chunks = list(processor.process([(doc_id, filename, file_bytes)]))

    assert len(chunks) == 2
    assert all(isinstance(chunk, tuple) and len(chunk) == 2 for chunk in chunks)
    assert all(chunk[0] == doc_id for chunk in chunks)
    assert chunks[0][1] == "chunk-1"
    assert chunks[1][1] == "chunk-2"
    mock_get_text_extractor.assert_called_once_with(filename)
    mock_extractor.extract_text_from.assert_called_once_with(file_bytes, filename)
    # Verify _split_content was called once (content is stripped by _validate_content)
    mock_split_content.assert_called_once()


def test_process_multiple_valid_files(processor):
    """Test processing multiple valid files produces chunks from all files."""
    content1 = "First document content. " * 50
    content2 = "Second document content. " * 50
    doc_id1 = uuid4()
    doc_id2 = uuid4()
    filename1 = "doc1.txt"
    filename2 = "doc2.pdf"
    file_bytes1 = content1.encode("utf-8")
    file_bytes2 = content2.encode("utf-8")

    extractor1 = Mock()
    extractor1.extract_text_from.return_value = content1
    extractor2 = Mock()
    extractor2.extract_text_from.return_value = content2

    with patch(
        "src.components.ingestion.document_processor.get_text_extractor",
        side_effect=[extractor1, extractor2],
    ) as mock_get_text_extractor, patch.object(
        processor,
        "_split_content",
        side_effect=[["chunk-1", "chunk-2"], ["chunk-3"]],
    ) as mock_split_content:
        chunks = list(processor.process([(doc_id1, filename1, file_bytes1), (doc_id2, filename2, file_bytes2)]))

    assert len(chunks) == 3
    assert chunks[0] == (doc_id1, "chunk-1")
    assert chunks[1] == (doc_id1, "chunk-2")
    assert chunks[2] == (doc_id2, "chunk-3")
    assert mock_get_text_extractor.call_count == 2
    assert extractor1.extract_text_from.call_count == 1
    assert extractor2.extract_text_from.call_count == 1
    assert mock_split_content.call_count == 2


def test_process_yields_chunks_incrementally(processor):
    """Test that process() yields chunks as a generator (streaming behavior)."""
    content = "Test content. " * 100
    doc_id = uuid4()
    filename = "test.txt"
    file_bytes = content.encode("utf-8")

    mock_extractor = Mock()
    mock_extractor.extract_text_from.return_value = content

    with patch(
        "src.components.ingestion.document_processor.get_text_extractor",
        return_value=mock_extractor,
    ), patch.object(
        processor, "_split_content", return_value=["chunk-1", "chunk-2"]
    ):
        result = processor.process([(doc_id, filename, file_bytes)])

        assert hasattr(result, "__iter__")
        assert hasattr(result, "__next__")

        first_chunk = next(result)
        assert isinstance(first_chunk, tuple)
        assert len(first_chunk) == 2
        assert first_chunk[0] == doc_id
        assert first_chunk[1] == "chunk-1"


# ========================================
# Edge Cases and Error Handling
# ========================================


def test_process_empty_file_list_raises_error(processor):
    """Test that processing an empty file list raises unprocessable_entity_error."""
    with pytest.raises(Exception) as exc_info:
        list(processor.process([]))

    assert "No files provided" in str(exc_info.value) or "NO_FILES_PROVIDED" in str(exc_info.value)


def test_process_unsupported_file_type_raises_error(processor):
    """Test that unsupported file types bubble up as ValueError."""
    doc_id = uuid4()
    filename = "test.unsupported"
    file_bytes = b"content"

    with patch(
        "src.components.ingestion.document_processor.get_text_extractor",
        side_effect=ValueError("Unsupported file type"),
    ):
        with pytest.raises(ValueError, match="Unsupported file type"):
            list(processor.process([(doc_id, filename, file_bytes)]))


def test_process_extraction_failure_skips_file(processor):
    """Test that files that fail extraction are skipped."""
    doc_id = uuid4()
    filename = "test.pdf"
    file_bytes = b"content"

    mock_extractor = Mock()
    mock_extractor.extract_text_from.side_effect = Exception("Extraction failed")

    with patch(
        "src.components.ingestion.document_processor.get_text_extractor",
        return_value=mock_extractor,
    ) as mock_get_text_extractor:
        with pytest.raises(Exception) as exc_info:
            list(processor.process([(doc_id, filename, file_bytes)]))

        assert "No valid document chunks" in str(exc_info.value) or "NO_VALID_DOCUMENT_CHUNKS" in str(exc_info.value)
        mock_get_text_extractor.assert_called_once_with(filename)
        mock_extractor.extract_text_from.assert_called_once_with(file_bytes, filename)


def test_process_validation_failure_skips_file(processor):
    """Test that files that fail validation are skipped."""
    content = "Test content"
    doc_id = uuid4()
    filename = "test.txt"
    file_bytes = content.encode("utf-8")

    mock_extractor = Mock()
    mock_extractor.extract_text_from.return_value = content

    with patch(
        "src.components.ingestion.document_processor.get_text_extractor",
        return_value=mock_extractor,
    ), patch.object(
        processor,
        "_validate_content",
        return_value=(False, None),
    ), patch.object(
        processor, "_split_content"
    ) as mock_split_content:
        with pytest.raises(Exception) as exc_info:
            list(processor.process([(doc_id, filename, file_bytes)]))

        assert "No valid document chunks" in str(exc_info.value) or "NO_VALID_DOCUMENT_CHUNKS" in str(exc_info.value)
        mock_split_content.assert_not_called()


def test_process_empty_content_after_validation_skips_file(processor):
    """Test that files with empty content after validation are skipped."""
    content = "Test content"
    doc_id = uuid4()
    filename = "test.txt"
    file_bytes = content.encode("utf-8")

    mock_extractor = Mock()
    mock_extractor.extract_text_from.return_value = content

    with patch(
        "src.components.ingestion.document_processor.get_text_extractor",
        return_value=mock_extractor,
    ), patch.object(
        processor,
        "_validate_content",
        return_value=(True, ""),
    ), patch.object(
        processor, "_split_content"
    ) as mock_split_content:
        with pytest.raises(Exception) as exc_info:
            list(processor.process([(doc_id, filename, file_bytes)]))

        assert "No valid document chunks" in str(exc_info.value) or "NO_VALID_DOCUMENT_CHUNKS" in str(exc_info.value)
        mock_split_content.assert_not_called()


def test_process_mixed_valid_and_invalid_files(processor):
    """Test processing mixed valid and invalid files only yields chunks from valid files."""
    valid_content = "Valid document content. " * 50
    invalid_content = "Invalid"
    doc_id1 = uuid4()
    doc_id2 = uuid4()
    filename1 = "valid.txt"
    filename2 = "invalid.txt"
    file_bytes1 = valid_content.encode("utf-8")
    file_bytes2 = invalid_content.encode("utf-8")

    valid_extractor = Mock()
    valid_extractor.extract_text_from.return_value = valid_content
    invalid_extractor = Mock()
    invalid_extractor.extract_text_from.return_value = invalid_content

    with patch(
        "src.components.ingestion.document_processor.get_text_extractor",
        side_effect=[valid_extractor, invalid_extractor],
    ), patch.object(
        processor,
        "_validate_content",
        side_effect=[(True, valid_content), (False, None)],
    ), patch.object(
        processor,
        "_split_content",
        return_value=["chunk-a", "chunk-b"],
    ):
        chunks = list(processor.process([(doc_id1, filename1, file_bytes1), (doc_id2, filename2, file_bytes2)]))

    assert len(chunks) == 2
    assert chunks[0] == (doc_id1, "chunk-a")
    assert chunks[1] == (doc_id1, "chunk-b")


def test_process_filters_empty_chunks(processor):
    """Test that empty or whitespace-only chunks are filtered out."""
    content = "Valid content for testing"
    doc_id = uuid4()
    filename = "test.txt"
    file_bytes = content.encode("utf-8")

    mock_extractor = Mock()
    mock_extractor.extract_text_from.return_value = content

    with patch(
        "src.components.ingestion.document_processor.get_text_extractor",
        return_value=mock_extractor,
    ), patch.object(
        processor,
        "_validate_content",
        return_value=(True, content),
    ), patch.object(
        processor,
        "_split_content",
        return_value=["Valid chunk", "   ", "", "Another valid chunk"],
    ):
        chunks = list(processor.process([(doc_id, filename, file_bytes)]))

    assert len(chunks) == 2
    assert chunks[0] == (doc_id, "Valid chunk")
    assert chunks[1] == (doc_id, "Another valid chunk")
