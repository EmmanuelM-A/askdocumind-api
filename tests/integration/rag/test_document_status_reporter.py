# Integration tests for DocumentStatusReporter against a real PostgreSQL database with no mocks.
# The reporter commits through its own sessions, so rows are really committed and read back on a
# fresh connection, and every test deletes the rows it created. Rows are built from table metadata.

import importlib
import pkgutil
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import select

from src.database.session import DatabaseSessionManager
from src.rag.services.report.document_status_reporter import DocumentStatusReporter
from src.rag.services.report.status_reporter import (
    ProcessingStatus,
    StatusConflict,
    StatusReportFailed,
)
from src.uploads.domain.document import DocumentStatus
from src.uploads.models.document import Document
from src.uploads.repository.document_repository_impl import DocumentRepositoryImpl


def _import_all_models():
    import src

    for info in pkgutil.walk_packages(src.__path__, "src.", onerror=lambda name: None):
        if ".models" in info.name:
            importlib.import_module(info.name)


_import_all_models()

pytestmark = pytest.mark.asyncio

DOCS = Document.__table__
MAX_CHARS = 512


def _dummy(column):
    column_type = column.type
    if isinstance(column_type, sa.Enum) and column_type.enums:
        return column_type.enums[0]
    python_type = column_type.python_type
    values = {
        str: f"test-{uuid.uuid4().hex[:8]}",
        int: 1,
        float: 1.0,
        bool: False,
        bytes: b"x",
        dict: {},
        list: [],
        uuid.UUID: uuid.uuid4(),
        datetime: datetime.now(timezone.utc),
    }
    return values[python_type] if python_type in values else python_type()


async def _insert(session, table, created, **overrides):
    values = dict(overrides)
    for column in table.columns:
        if column.name in values:
            continue
        if column.foreign_keys:
            if column.nullable:
                continue
            foreign_key = next(iter(column.foreign_keys))
            parent = await _insert(session, foreign_key.column.table, created)
            values[column.name] = parent[foreign_key.column.name]
        elif column.primary_key:
            values[column.name] = _dummy(column)
        elif (
            column.nullable
            or column.default is not None
            or column.server_default is not None
        ):
            continue
        else:
            values[column.name] = _dummy(column)
    result = await session.execute(table.insert().values(**values).returning(table))
    row = dict(result.mappings().one())
    created.append((table, row["id"]))
    return row


def _status(row):
    return DocumentStatus(row["status"])


@pytest_asyncio.fixture
async def created(manager):
    rows = []
    yield rows
    async with manager.get_session() as session:
        for table, row_id in reversed(rows):
            await session.execute(table.delete().where(table.c.id == row_id))


@pytest_asyncio.fixture
async def make_document(manager, created):
    async def _make(status, **overrides):
        values = dict(overrides)
        if "updated_at" in DOCS.c and "updated_at" not in values:
            values["updated_at"] = datetime.now(timezone.utc) - timedelta(days=1)
        async with manager.get_session() as session:
            row = await _insert(session, DOCS, created, status=status, **values)
        return row["id"]

    return _make


@pytest.fixture
def reporter(manager, created):
    return DocumentStatusReporter(manager, DocumentRepositoryImpl)


@pytest.fixture
def read(manager):
    async def _read(document_id):
        async with manager.engine.connect() as conn:
            result = await conn.execute(select(DOCS).where(DOCS.c.id == document_id))
            return result.mappings().one()

    return _read


class TestTransitions:
    @pytest.mark.parametrize(
        "start, status, expected",
        [
            (
                DocumentStatus.UPLOADED,
                ProcessingStatus.PROCESSING,
                DocumentStatus.PROCESSING,
            ),
            (
                DocumentStatus.PROCESSING,
                ProcessingStatus.COMPLETED,
                DocumentStatus.COMPLETED,
            ),
            (DocumentStatus.PROCESSING, ProcessingStatus.FAILED, DocumentStatus.FAILED),
        ],
    )
    async def test_status_is_committed_and_visible_to_other_connections(
        self, reporter, make_document, read, start, status, expected
    ):
        document_id = await make_document(start)

        await reporter.report(document_id, status)

        assert _status(await read(document_id)) == expected

    async def test_updated_at_moves_forward(self, reporter, make_document, read):
        document_id = await make_document(DocumentStatus.UPLOADED)

        await reporter.report(document_id, ProcessingStatus.PROCESSING)

        updated_at = (await read(document_id))["updated_at"]
        assert updated_at > datetime.now(timezone.utc) - timedelta(hours=12)

    async def test_full_success_lifecycle(self, reporter, make_document, read):
        document_id = await make_document(DocumentStatus.UPLOADED)

        await reporter.report(document_id, ProcessingStatus.PROCESSING)
        assert _status(await read(document_id)) == DocumentStatus.PROCESSING

        await reporter.report(document_id, ProcessingStatus.COMPLETED)
        assert _status(await read(document_id)) == DocumentStatus.COMPLETED

    async def test_other_documents_are_untouched(self, reporter, make_document, read):
        target = await make_document(DocumentStatus.UPLOADED)
        other = await make_document(DocumentStatus.UPLOADED)

        await reporter.report(target, ProcessingStatus.PROCESSING)

        assert _status(await read(other)) == DocumentStatus.UPLOADED


class TestErrorMessage:
    async def test_failed_stores_the_message(self, reporter, make_document, read):
        document_id = await make_document(DocumentStatus.PROCESSING)

        await reporter.report(
            document_id, ProcessingStatus.FAILED, "extraction crashed"
        )

        assert (await read(document_id))["error_message"] == "extraction crashed"

    async def test_completed_clears_an_old_message(self, reporter, make_document, read):
        document_id = await make_document(
            DocumentStatus.PROCESSING, error_message="old failure"
        )

        await reporter.report(document_id, ProcessingStatus.COMPLETED, "ignored")

        assert (await read(document_id))["error_message"] is None

    async def test_nul_characters_are_removed_before_storing(
        self, reporter, make_document, read
    ):
        document_id = await make_document(DocumentStatus.PROCESSING)

        await reporter.report(document_id, ProcessingStatus.FAILED, "bad\x00 value")

        assert (await read(document_id))["error_message"] == "bad value"

    async def test_long_unicode_message_is_cut_to_the_column_limit(
        self, reporter, make_document, read
    ):
        document_id = await make_document(DocumentStatus.PROCESSING)

        await reporter.report(document_id, ProcessingStatus.FAILED, "é" * 2000)

        assert (await read(document_id))["error_message"] == "é" * MAX_CHARS


class TestConflicts:
    @pytest.mark.parametrize(
        "start, status",
        [
            (DocumentStatus.UPLOADED, ProcessingStatus.COMPLETED),
            (DocumentStatus.UPLOADED, ProcessingStatus.FAILED),
            (DocumentStatus.PENDING, ProcessingStatus.PROCESSING),
            (DocumentStatus.COMPLETED, ProcessingStatus.PROCESSING),
            (DocumentStatus.FAILED, ProcessingStatus.COMPLETED),
        ],
    )
    async def test_disallowed_transition_raises_conflict_and_changes_nothing(
        self, reporter, make_document, read, start, status
    ):
        document_id = await make_document(start)

        with pytest.raises(StatusConflict):
            await reporter.report(document_id, status)

        assert _status(await read(document_id)) == start

    async def test_unknown_document_raises_conflict(self, reporter):
        with pytest.raises(StatusConflict):
            await reporter.report(uuid.uuid4(), ProcessingStatus.PROCESSING)

    async def test_repeating_a_report_raises_conflict(
        self, reporter, make_document, read
    ):
        document_id = await make_document(DocumentStatus.PROCESSING)
        await reporter.report(document_id, ProcessingStatus.COMPLETED)

        with pytest.raises(StatusConflict):
            await reporter.report(document_id, ProcessingStatus.COMPLETED)

        assert _status(await read(document_id)) == DocumentStatus.COMPLETED


class TestFailures:
    async def test_unreachable_database_raises_report_failed(self):
        dead = DatabaseSessionManager(
            "postgresql+asyncpg://user:secret@127.0.0.1:1/none"
        )
        try:
            reporter = DocumentStatusReporter(dead, DocumentRepositoryImpl)
            with pytest.raises(StatusReportFailed) as exc:
                await reporter.report(uuid.uuid4(), ProcessingStatus.PROCESSING)
            assert exc.value.__cause__ is not None
        finally:
            await dead.disconnect()
