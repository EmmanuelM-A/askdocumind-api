"""
Integration tests for DocumentRepositoryImpl.

now() is fixed for the whole test transaction, so tests that depend on time
ordering set created_at/updated_at explicitly. The stale-document tests date
their rows before 2000 so real rows can never fall inside the cutoff.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

import src.database.models  # noqa: F401  registers every model for the mappers
from src.auth.models.user import User
from src.chat_session.models.chat_session import ChatSession
from src.database.utils import Pagination
from src.exceptions.base import ApiException
from src.uploads.domain.document import DocumentStatus
from src.uploads.models.document import Document
from src.uploads.repository.document_repository import DocumentSearchFilter
from src.uploads.repository.document_repository_impl import DocumentRepositoryImpl

pytestmark = pytest.mark.asyncio

_INTERNAL_ERROR = status.HTTP_500_INTERNAL_SERVER_ERROR
_CUTOFF = datetime(2000, 1, 1, tzinfo=UTC)


def _document(chat_session_id, filename=None, **overrides):
    values = {
        "chat_session_id": chat_session_id,
        "original_filename": filename or f"file-{uuid.uuid4().hex[:8]}.pdf",
        "object_key": f"test/{uuid.uuid4()}",
        "content_type": "application/pdf",
        "size_bytes": 0,
        "checksum": "",
    }
    values.update(overrides)
    return Document(**values)


async def _new_chat_session(session):
    user = User()
    session.add(user)
    await session.flush()
    chat_session = ChatSession(user_id=user.id, title="test")
    session.add(chat_session)
    await session.flush()
    return chat_session.id


async def _add(repo, chat_session_id, filename=None, **overrides):
    return await repo.create(_document(chat_session_id, filename, **overrides))


async def _row(session, document_id):
    result = await session.execute(
        select(
            Document.status,
            Document.error_message,
            Document.size_bytes,
            Document.checksum,
            Document.updated_at,
        ).where(Document.id == document_id)
    )
    return result.one_or_none()


@pytest.fixture
def repo(session):
    return DocumentRepositoryImpl(session)


@pytest_asyncio.fixture
async def chat_session_id(session):
    return await _new_chat_session(session)


class TestCreate:
    async def test_persists_document_with_defaults(
        self, repo, session, chat_session_id
    ):
        document = _document(chat_session_id, "notes.pdf")

        created = await repo.create(document)
        await session.refresh(created)

        assert created is document
        assert isinstance(created.id, uuid.UUID)
        assert created.status == DocumentStatus.PENDING
        assert created.error_message is None
        assert created.created_at is not None
        assert (await _row(session, created.id)) is not None

    async def test_duplicate_filename_in_same_chat_session_raises(
        self, repo, chat_session_id
    ):
        await _add(repo, chat_session_id, "same.pdf")

        with pytest.raises(ApiException) as exc:
            await _add(repo, chat_session_id, "same.pdf")
        assert exc.value.status_code == _INTERNAL_ERROR

    async def test_unknown_chat_session_raises(self, repo):
        with pytest.raises(ApiException) as exc:
            await _add(repo, uuid.uuid4())
        assert exc.value.status_code == _INTERNAL_ERROR


class TestCreateMany:
    async def test_persists_all_and_returns_ids_in_order(
        self, repo, session, chat_session_id
    ):
        documents = [_document(chat_session_id) for _ in range(3)]

        ids = await repo.create_many(documents)

        assert ids == [d.id for d in documents]
        assert await repo.count(chat_session_id) == 3
        assert await repo.create_many([]) == []

    async def test_duplicate_filename_within_batch_raises(self, repo, chat_session_id):
        batch = [
            _document(chat_session_id, "dup.pdf"),
            _document(chat_session_id, "dup.pdf"),
        ]

        with pytest.raises(ApiException) as exc:
            await repo.create_many(batch)
        assert exc.value.status_code == _INTERNAL_ERROR


class TestListByCriteria:
    async def test_returns_session_documents_newest_first(
        self, repo, session, chat_session_id
    ):
        base = datetime(2024, 1, 1, tzinfo=UTC)
        oldest = await _add(repo, chat_session_id, created_at=base)
        newest = await _add(repo, chat_session_id, created_at=base + timedelta(days=2))
        tied = [
            await _add(repo, chat_session_id, created_at=base + timedelta(days=1))
            for _ in range(2)
        ]
        other_session = await _new_chat_session(session)
        await _add(repo, other_session)

        result = await repo.list_by_criteria(chat_session_id)

        tied_desc = sorted((d.id for d in tied), reverse=True)
        assert [d.id for d in result] == [newest.id, *tied_desc, oldest.id]

    async def test_filename_filter_is_case_insensitive_and_literal(
        self, repo, chat_session_id
    ):
        underscore = await _add(repo, chat_session_id, "Report_2024.pdf")
        await _add(repo, chat_session_id, "reportX2024.pdf")
        percent = await _add(repo, chat_session_id, "100%.txt")
        await _add(repo, chat_session_id, "100abc.txt")

        by_underscore = await repo.list_by_criteria(
            chat_session_id, DocumentSearchFilter(filename="RT_2")
        )
        by_percent = await repo.list_by_criteria(
            chat_session_id, DocumentSearchFilter(filename="0%")
        )

        assert [d.id for d in by_underscore] == [underscore.id]
        assert [d.id for d in by_percent] == [percent.id]

    async def test_combined_filters_narrow_results(self, repo, chat_session_id):
        match = await _add(
            repo, chat_session_id, "a.pdf", status=DocumentStatus.COMPLETED
        )
        await _add(repo, chat_session_id, "b.pdf", status=DocumentStatus.FAILED)
        await _add(repo, chat_session_id, "c.txt", status=DocumentStatus.COMPLETED)

        result = await repo.list_by_criteria(
            chat_session_id,
            DocumentSearchFilter(filename=".pdf", status=DocumentStatus.COMPLETED),
        )
        no_match = await repo.list_by_criteria(
            chat_session_id, DocumentSearchFilter(filename="missing")
        )

        assert [d.id for d in result] == [match.id]
        assert no_match == []
        assert await repo.list_by_criteria(uuid.uuid4()) == []


class TestListByCriteriaPaginated:
    async def test_returns_requested_page_with_total(self, repo, chat_session_id):
        base = datetime(2024, 1, 1, tzinfo=UTC)
        documents = [
            await _add(repo, chat_session_id, created_at=base + timedelta(days=i))
            for i in range(5)
        ]

        page = await repo.list_by_criteria_paginated(
            chat_session_id, Pagination(page=2, limit=2)
        )

        assert page.total == 5
        assert [d.id for d in page.items] == [documents[2].id, documents[1].id]

    async def test_page_beyond_end_is_empty_but_keeps_total(
        self, repo, chat_session_id
    ):
        for _ in range(3):
            await _add(repo, chat_session_id)

        page = await repo.list_by_criteria_paginated(
            chat_session_id, Pagination(page=3, limit=2)
        )

        assert page.items == []
        assert page.total == 3


class TestGetById:
    async def test_returns_document_or_none(self, repo, chat_session_id):
        document = await _add(repo, chat_session_id)

        found = await repo.get_by_id(document.id)

        assert found is not None
        assert found.id == document.id
        assert await repo.get_by_id(uuid.uuid4()) is None


class TestCount:
    async def test_counts_only_the_given_chat_session(
        self, repo, session, chat_session_id
    ):
        other_session = await _new_chat_session(session)
        for _ in range(2):
            await _add(repo, chat_session_id)
        await _add(repo, other_session)

        assert await repo.count(chat_session_id) == 2
        assert await repo.count(uuid.uuid4()) == 0


class TestDelete:
    async def test_deletes_only_the_target_document(
        self, repo, session, chat_session_id
    ):
        target = await _add(repo, chat_session_id)
        survivor = await _add(repo, chat_session_id)

        await repo.delete(target.id)

        assert await _row(session, target.id) is None
        assert await _row(session, survivor.id) is not None

    async def test_unknown_document_raises(self, repo):
        with pytest.raises(ApiException) as exc:
            await repo.delete(uuid.uuid4())
        assert exc.value.status_code == _INTERNAL_ERROR


class TestDeleteMany:
    async def test_deletes_listed_and_counts_only_existing(
        self, repo, session, chat_session_id
    ):
        doomed = [await _add(repo, chat_session_id) for _ in range(2)]
        survivor = await _add(repo, chat_session_id)

        deleted = await repo.delete_many([d.id for d in doomed] + [uuid.uuid4()])

        assert deleted == 2
        assert await _row(session, survivor.id) is not None
        assert await repo.delete_many([]) == 0


class TestUpdateDocumentStatus:
    async def test_sets_and_clears_error_message(self, repo, session, chat_session_id):
        document = await _add(repo, chat_session_id)

        await repo.update_document_status(
            document.id, DocumentStatus.FAILED, "extraction failed"
        )
        failed = await _row(session, document.id)
        await repo.update_document_status(document.id, DocumentStatus.COMPLETED)
        completed = await _row(session, document.id)

        assert (failed.status, failed.error_message) == (
            DocumentStatus.FAILED,
            "extraction failed",
        )
        assert (completed.status, completed.error_message) == (
            DocumentStatus.COMPLETED,
            None,
        )

    async def test_unknown_document_raises(self, repo):
        with pytest.raises(ApiException) as exc:
            await repo.update_document_status(uuid.uuid4(), DocumentStatus.FAILED)
        assert exc.value.status_code == _INTERNAL_ERROR


class TestTransitionDocumentStatus:
    async def test_transitions_from_allowed_status_and_bumps_updated_at(
        self, repo, session, chat_session_id
    ):
        old = datetime(1999, 1, 1, tzinfo=UTC)
        document = await _add(
            repo, chat_session_id, status=DocumentStatus.PROCESSING, updated_at=old
        )

        changed = await repo.transition_document_status(
            document.id,
            {DocumentStatus.UPLOADED, DocumentStatus.PROCESSING},
            DocumentStatus.FAILED,
            "timed out",
        )

        row = await _row(session, document.id)
        assert changed is True
        assert row.status == DocumentStatus.FAILED
        assert row.error_message == "timed out"
        assert row.updated_at > old

    async def test_disallowed_or_empty_from_statuses_leave_row_unchanged(
        self, repo, session, chat_session_id
    ):
        document = await _add(repo, chat_session_id, status=DocumentStatus.COMPLETED)

        disallowed = await repo.transition_document_status(
            document.id, [DocumentStatus.PROCESSING], DocumentStatus.FAILED
        )
        empty = await repo.transition_document_status(
            document.id, [], DocumentStatus.FAILED
        )
        unknown = await repo.transition_document_status(
            uuid.uuid4(), [DocumentStatus.COMPLETED], DocumentStatus.FAILED
        )

        assert (disallowed, empty, unknown) == (False, False, False)
        assert (await _row(session, document.id)).status == DocumentStatus.COMPLETED


class TestListStaleDocuments:
    async def test_returns_oldest_matching_documents_up_to_limit(
        self, repo, chat_session_id
    ):
        def at(year, month=1):
            return datetime(year, month, 1, tzinfo=UTC)

        processing = DocumentStatus.PROCESSING
        oldest = await _add(
            repo, chat_session_id, status=processing, updated_at=at(1998)
        )
        middle = await _add(
            repo, chat_session_id, status=processing, updated_at=at(1999)
        )
        await _add(repo, chat_session_id, status=processing, updated_at=at(1999, 6))
        await _add(repo, chat_session_id, status=processing)
        await _add(
            repo, chat_session_id, status=DocumentStatus.UPLOADED, updated_at=at(1997)
        )

        result = await repo.list_stale_documents(processing, _CUTOFF, limit=2)

        assert [d.id for d in result] == [oldest.id, middle.id]


class TestMarkUploaded:
    async def test_marks_pending_document_only_once(
        self, repo, session, chat_session_id
    ):
        document = await _add(repo, chat_session_id)

        first = await repo.mark_uploaded(document.id, 2048, "abc123")
        second = await repo.mark_uploaded(document.id, 1, "other")

        row = await _row(session, document.id)
        assert (first, second) == (True, False)
        assert (row.status, row.size_bytes, row.checksum) == (
            DocumentStatus.UPLOADED,
            2048,
            "abc123",
        )


class TestDeleteByChatSession:
    async def test_deletes_session_documents_and_leaves_others(
        self, repo, session, chat_session_id
    ):
        other_session = await _new_chat_session(session)
        for _ in range(2):
            await _add(repo, chat_session_id)
        survivor = await _add(repo, other_session)

        assert await repo.delete_by_chat_session(chat_session_id) == 2
        assert await repo.count(chat_session_id) == 0
        assert await _row(session, survivor.id) is not None
        assert await repo.delete_by_chat_session(uuid.uuid4()) == 0


CALLS = {
    "create": lambda r: r.create(_document(uuid.uuid4())),
    "create_many": lambda r: r.create_many([_document(uuid.uuid4())]),
    "list_by_criteria": lambda r: r.list_by_criteria(uuid.uuid4()),
    "list_by_criteria_paginated": lambda r: r.list_by_criteria_paginated(
        uuid.uuid4(), Pagination()
    ),
    "get_by_id": lambda r: r.get_by_id(uuid.uuid4()),
    "count": lambda r: r.count(uuid.uuid4()),
    "delete": lambda r: r.delete(uuid.uuid4()),
    "delete_many": lambda r: r.delete_many([uuid.uuid4()]),
    "update_document_status": lambda r: r.update_document_status(
        uuid.uuid4(), DocumentStatus.FAILED
    ),
    "transition_document_status": lambda r: r.transition_document_status(
        uuid.uuid4(), [DocumentStatus.PENDING], DocumentStatus.FAILED
    ),
    "list_stale_documents": lambda r: r.list_stale_documents(
        DocumentStatus.PROCESSING, _CUTOFF
    ),
    "mark_uploaded": lambda r: r.mark_uploaded(uuid.uuid4(), 1, "x"),
    "delete_by_chat_session": lambda r: r.delete_by_chat_session(uuid.uuid4()),
}


class TestDatabaseFailures:
    async def test_every_method_maps_database_errors_to_internal_error(
        self, repo, session
    ):
        error = AsyncMock(side_effect=SQLAlchemyError("boom"))
        with patch.object(session, "execute", error), patch.object(
            session, "flush", error
        ):
            for name, call in CALLS.items():
                with pytest.raises(ApiException) as exc:
                    await call(repo)
                assert exc.value.status_code == _INTERNAL_ERROR, name
