"""
Integration tests for the Sweeper against a real database and S3 bucket.

The sweeper looks at every document in the database, so the config moves the
cutoffs back to 2000 (2001 for retries) and the tests date their own rows
around them. Real rows are always newer and never inside a cutoff.
Only the ingestion runner is mocked, so retries can be observed without
running a real ingestion.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from src.config.configs import settings
from src.rag.models.chunk_embedding import ChunkEmbedding
from src.uploads.domain.document import DocumentStatus
from src.uploads.models.document import Document
from src.uploads.services.ingestion_service import IngestionRunner
from src.uploads.services.sweeper import Sweeper, SweeperConfig

pytestmark = pytest.mark.asyncio

_EXPIRED = datetime(1999, 1, 1, tzinfo=UTC)
_RETRYABLE = datetime(2000, 6, 1, tzinfo=UTC)


def _seconds_since(year):
    elapsed = datetime.now(UTC) - datetime(year, 1, 1, tzinfo=UTC)
    return int(elapsed.total_seconds())


def _config(**overrides):
    values = {
        "processing_timeout_seconds": _seconds_since(2000),
        "uploaded_max_age_seconds": _seconds_since(2000),
        "uploaded_retry_after_seconds": _seconds_since(2001),
        "pending_after_seconds": _seconds_since(2000),
    }
    values.update(overrides)
    return SweeperConfig(**values)


@pytest.fixture
def runner():
    return MagicMock(spec=IngestionRunner)


@pytest.fixture
def make_sweeper(manager, object_storage, runner):
    def _make(**overrides):
        return Sweeper(manager, object_storage, runner, _config(**overrides))

    return _make


@pytest_asyncio.fixture
async def chat_session_id(new_chat_session):
    return await new_chat_session()


@pytest_asyncio.fixture
async def make_document(manager, object_storage, chat_session_id):
    async def _make(status, updated_at=None, chunks=0):
        key = f"{chat_session_id}/{uuid.uuid4()}"
        object_storage.save(key, b"content")
        async with manager.get_session() as session:
            document = Document(
                chat_session_id=chat_session_id,
                original_filename=f"{uuid.uuid4().hex}.txt",
                object_key=key,
                content_type="text/plain",
                size_bytes=7,
                checksum="x",
                status=status,
            )
            if updated_at is not None:
                document.updated_at = updated_at
            session.add(document)
            await session.flush()
            session.add_all(
                ChunkEmbedding(
                    document_id=document.id,
                    chat_session_id=chat_session_id,
                    chunk_index=i,
                    chunk_text=f"chunk {i}",
                    embedding=[0.1] * settings.rag.EMBEDDING_DIMENSIONS,
                )
                for i in range(chunks)
            )
        return document

    return _make


async def _status(manager, document_id):
    async with manager.get_session() as session:
        result = await session.execute(
            select(Document.status).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()


async def _chunk_count(manager, document_id):
    async with manager.get_session() as session:
        result = await session.execute(
            select(func.count())
            .select_from(ChunkEmbedding)
            .where(ChunkEmbedding.document_id == document_id)
        )
        return result.scalar_one()


def _started_ids(runner):
    return {call.args[0].document_id for call in runner.start.call_args_list}


class TestUploadedRules:
    async def test_expired_uploaded_document_is_failed_and_not_retried(
        self, manager, make_sweeper, make_document, runner
    ):
        document = await make_document(DocumentStatus.UPLOADED, _EXPIRED)

        await make_sweeper().sweep_once()

        assert await _status(manager, document.id) == DocumentStatus.FAILED
        assert document.id not in _started_ids(runner)

    async def test_stuck_uploaded_document_is_retried(
        self, manager, make_sweeper, make_document, runner
    ):
        stuck = await make_document(DocumentStatus.UPLOADED, _RETRYABLE)
        fresh = await make_document(DocumentStatus.UPLOADED)

        await make_sweeper().sweep_once()

        started = _started_ids(runner)
        assert stuck.id in started
        assert fresh.id not in started
        assert await _status(manager, stuck.id) == DocumentStatus.UPLOADED


class TestProcessingRule:
    async def test_timed_out_processing_is_failed_and_chunks_removed(
        self, manager, make_sweeper, make_document
    ):
        timed_out = await make_document(DocumentStatus.PROCESSING, _EXPIRED, chunks=2)
        fresh = await make_document(DocumentStatus.PROCESSING, chunks=2)

        await make_sweeper().sweep_once()

        assert await _status(manager, timed_out.id) == DocumentStatus.FAILED
        assert await _chunk_count(manager, timed_out.id) == 0
        assert await _status(manager, fresh.id) == DocumentStatus.PROCESSING
        assert await _chunk_count(manager, fresh.id) == 2

    async def test_only_batch_limit_oldest_documents_are_handled(
        self, manager, make_sweeper, make_document
    ):
        documents = [
            await make_document(
                DocumentStatus.PROCESSING, _EXPIRED.replace(month=month)
            )
            for month in (3, 1, 2)
        ]

        await make_sweeper(batch_limit=2).sweep_once()

        statuses = [await _status(manager, d.id) for d in documents]
        assert statuses == [
            DocumentStatus.PROCESSING,
            DocumentStatus.FAILED,
            DocumentStatus.FAILED,
        ]


class TestPendingRule:
    async def test_abandoned_pending_document_and_file_are_removed(
        self, manager, object_storage, make_sweeper, make_document
    ):
        abandoned = await make_document(DocumentStatus.PENDING, _EXPIRED)
        fresh = await make_document(DocumentStatus.PENDING)

        await make_sweeper().sweep_once()

        assert await _status(manager, abandoned.id) is None
        assert object_storage.exists(abandoned.object_key) is False
        assert await _status(manager, fresh.id) == DocumentStatus.PENDING
        assert object_storage.exists(fresh.object_key) is True


class TestSweepOnce:
    async def test_failing_rule_does_not_stop_later_rules(
        self, manager, make_sweeper, make_document, runner
    ):
        runner.start.side_effect = RuntimeError("runner is down")
        await make_document(DocumentStatus.UPLOADED, _RETRYABLE)
        timed_out = await make_document(DocumentStatus.PROCESSING, _EXPIRED)
        abandoned = await make_document(DocumentStatus.PENDING, _EXPIRED)

        await make_sweeper().sweep_once()

        assert runner.start.called
        assert await _status(manager, timed_out.id) == DocumentStatus.FAILED
        assert await _status(manager, abandoned.id) is None

    async def test_completed_and_failed_documents_are_left_alone(
        self, manager, object_storage, make_sweeper, make_document, runner
    ):
        completed = await make_document(DocumentStatus.COMPLETED, _EXPIRED, chunks=1)
        failed = await make_document(DocumentStatus.FAILED, _EXPIRED)

        await make_sweeper().sweep_once()

        assert await _status(manager, completed.id) == DocumentStatus.COMPLETED
        assert await _chunk_count(manager, completed.id) == 1
        assert await _status(manager, failed.id) == DocumentStatus.FAILED
        assert object_storage.exists(failed.object_key) is True
        assert not {completed.id, failed.id} & _started_ids(runner)


class TestLifecycle:
    async def test_loop_survives_errors_until_stopped(self, make_sweeper):
        sweeper = make_sweeper(interval_seconds=0)
        second_pass = asyncio.Event()
        calls = 0

        async def sweep_once():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("first pass fails")
            second_pass.set()

        sweeper.sweep_once = sweep_once
        sweeper.start()
        await asyncio.wait_for(second_pass.wait(), timeout=10)
        await sweeper.stop()
        calls_at_stop = calls
        await asyncio.sleep(0.05)

        assert calls_at_stop >= 2
        assert calls == calls_at_stop

    async def test_stop_without_start_is_a_no_op(self, make_sweeper):
        sweeper = make_sweeper()

        await sweeper.stop()
        await sweeper.stop()
