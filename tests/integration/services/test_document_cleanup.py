"""Tests for the DocumentCleanupService."""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from src.config.configs import settings


@pytest.fixture
def mock_document_repo():
    repo = Mock()
    repo.get_stuck_processing_ids = AsyncMock(return_value=[])
    repo.get_all_failed_ids = AsyncMock(return_value=[])
    repo.bulk_update_processing_status = AsyncMock(return_value=0)
    repo.delete_many = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_chunk_repo():
    repo = Mock()
    repo.delete_orphaned_web_chunks = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def cleanup_service(mock_document_repo, mock_chunk_repo):
    from src.api.services.documents.document_cleanup import DocumentCleanupService

    return DocumentCleanupService(
        document_repo=mock_document_repo,
        chunk_repo=mock_chunk_repo,
    )


# ==================== mark_stuck_documents_as_failed ====================


@pytest.mark.asyncio
async def test_mark_stuck_no_stuck_docs_returns_zero(cleanup_service, mock_document_repo):
    """Returns 0 and skips bulk_update when no stuck docs exist."""
    mock_document_repo.get_stuck_processing_ids.return_value = []

    result = await cleanup_service.mark_stuck_documents_as_failed()

    assert result == 0
    mock_document_repo.bulk_update_processing_status.assert_not_called()


@pytest.mark.asyncio
async def test_mark_stuck_marks_all_in_batches(cleanup_service, mock_document_repo, monkeypatch):
    """bulk_update_processing_status is called once per batch with FAILED status."""
    from src.config.constants import ProcessingStatus

    monkeypatch.setattr(settings.files, "DOC_CLEANUP_BATCH_SIZE", 2)

    ids = [uuid4(), uuid4(), uuid4()]
    mock_document_repo.get_stuck_processing_ids.return_value = ids
    mock_document_repo.bulk_update_processing_status.return_value = 1

    result = await cleanup_service.mark_stuck_documents_as_failed(batch_size=2)

    assert result == 2  # 2 successful batches (1 + 1), third batch has 1 item -> 1 + 1 = 2
    assert mock_document_repo.bulk_update_processing_status.call_count == 2
    first_call_kwargs = mock_document_repo.bulk_update_processing_status.call_args_list[0].kwargs
    assert first_call_kwargs["status"] == ProcessingStatus.FAILED
    assert len(first_call_kwargs["document_ids"]) == 2


@pytest.mark.asyncio
async def test_mark_stuck_continues_after_batch_error(cleanup_service, mock_document_repo):
    """A failing batch is logged and skipped; remaining batches still run."""
    ids = [uuid4(), uuid4()]
    mock_document_repo.get_stuck_processing_ids.return_value = ids
    mock_document_repo.bulk_update_processing_status.side_effect = [
        Exception("DB error"),
        1,
    ]

    result = await cleanup_service.mark_stuck_documents_as_failed(batch_size=1)

    assert result == 1
    assert mock_document_repo.bulk_update_processing_status.call_count == 2


# ==================== delete_failed_documents ====================


@pytest.mark.asyncio
async def test_delete_failed_no_failed_docs_returns_zero(cleanup_service, mock_document_repo):
    """Returns 0 and skips delete_many when no failed docs exist."""
    mock_document_repo.get_all_failed_ids.return_value = []

    result = await cleanup_service.delete_failed_documents()

    assert result == 0
    mock_document_repo.delete_many.assert_not_called()


@pytest.mark.asyncio
async def test_delete_failed_deletes_in_batches(cleanup_service, mock_document_repo):
    """delete_many is called once per batch."""
    ids = [uuid4(), uuid4(), uuid4()]
    mock_document_repo.get_all_failed_ids.return_value = ids
    mock_document_repo.delete_many.return_value = 1

    result = await cleanup_service.delete_failed_documents(batch_size=2)

    assert result == 2
    assert mock_document_repo.delete_many.call_count == 2


@pytest.mark.asyncio
async def test_delete_failed_continues_after_batch_error(cleanup_service, mock_document_repo):
    """A failing delete batch is logged and skipped; remaining batches still run."""
    ids = [uuid4(), uuid4()]
    mock_document_repo.get_all_failed_ids.return_value = ids
    mock_document_repo.delete_many.side_effect = [Exception("DB error"), 1]

    result = await cleanup_service.delete_failed_documents(batch_size=1)

    assert result == 1
    assert mock_document_repo.delete_many.call_count == 2


# ==================== delete_orphaned_web_chunks ====================


@pytest.mark.asyncio
async def test_delete_orphaned_web_chunks_delegates_to_repo(cleanup_service, mock_chunk_repo):
    """delete_orphaned_web_chunks is called once with a datetime cutoff."""
    from datetime import datetime

    mock_chunk_repo.delete_orphaned_web_chunks.return_value = 5

    result = await cleanup_service.delete_orphaned_web_chunks()

    assert result == 5
    mock_chunk_repo.delete_orphaned_web_chunks.assert_called_once()
    cutoff_arg = mock_chunk_repo.delete_orphaned_web_chunks.call_args.kwargs["cutoff"]
    assert isinstance(cutoff_arg, datetime)


@pytest.mark.asyncio
async def test_delete_orphaned_web_chunks_handles_repo_error(cleanup_service, mock_chunk_repo):
    """Returns 0 gracefully when the repo raises."""
    mock_chunk_repo.delete_orphaned_web_chunks.side_effect = Exception("DB error")

    result = await cleanup_service.delete_orphaned_web_chunks()

    assert result == 0
