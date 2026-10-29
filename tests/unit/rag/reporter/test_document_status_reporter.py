"""
Unit tests for DocumentStatusReporter. The session manager and the document repository
are replaced with mocks, because the reporter only coordinates them. It raises
StatusConflict and StatusReportFailed, not ApiException, so tests assert exception types.
"""

import logging
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.database.session import DatabaseSessionManager
from src.rag.services.report import document_status_reporter as reporter_module
from src.rag.services.report.document_status_reporter import DocumentStatusReporter
from src.rag.services.report.status_reporter import (
    ProcessingStatus,
    StatusConflict,
    StatusReporter,
    StatusReportFailed,
)
from src.uploads.domain.document import DocumentStatus
from src.uploads.repository.document_repository import DocumentRepository

pytestmark = pytest.mark.asyncio

MAX_CHARS = 512


class FakeSessionContext:
    def __init__(self, session, enter_error=None, exit_error=None):
        self._session = session
        self._enter_error = enter_error
        self._exit_error = exit_error
        self.exited = False

    async def __aenter__(self):
        if self._enter_error:
            raise self._enter_error
        return self._session

    async def __aexit__(self, *exc_info):
        self.exited = True
        if self._exit_error:
            raise self._exit_error
        return False


@pytest.fixture
def session():
    return AsyncMock()


@pytest.fixture
def session_manager(session):
    manager = MagicMock(spec=DatabaseSessionManager)
    manager.get_session.side_effect = lambda: FakeSessionContext(session)
    return manager


@pytest.fixture
def repository():
    repo = AsyncMock(spec=DocumentRepository)
    repo.transition_document_status.return_value = True
    return repo


@pytest.fixture
def repository_factory(repository):
    return MagicMock(return_value=repository)


@pytest.fixture
def reporter(session_manager, repository_factory):
    return DocumentStatusReporter(session_manager, repository_factory)


def sent_error_message(repository):
    return repository.transition_document_status.call_args.kwargs["error_message"]


class TestContract:
    async def test_is_a_status_reporter(self, reporter):
        assert isinstance(reporter, StatusReporter)

    async def test_every_processing_status_has_a_matching_document_status(self):
        for status in ProcessingStatus:
            assert DocumentStatus(status.value)
            assert reporter_module._ALLOWED_FROM[status]


class TestTransitions:
    @pytest.mark.parametrize(
        "status, expected_from, expected_to",
        [
            (
                ProcessingStatus.PROCESSING,
                [DocumentStatus.UPLOADED],
                DocumentStatus.PROCESSING,
            ),
            (
                ProcessingStatus.COMPLETED,
                [DocumentStatus.PROCESSING],
                DocumentStatus.COMPLETED,
            ),
            (
                ProcessingStatus.FAILED,
                [DocumentStatus.PROCESSING],
                DocumentStatus.FAILED,
            ),
        ],
    )
    async def test_requests_the_allowed_transition(
        self, reporter, repository, status, expected_from, expected_to
    ):
        document_id = uuid4()

        await reporter.report(document_id, status)

        repository.transition_document_status.assert_awaited_once_with(
            document_id=document_id,
            from_statuses=expected_from,
            to_status=expected_to,
            error_message=None,
        )

    async def test_repository_is_built_from_the_session_the_manager_opens(
        self, reporter, repository_factory, session
    ):
        await reporter.report(uuid4(), ProcessingStatus.PROCESSING)
        repository_factory.assert_called_once_with(session)

    async def test_session_is_closed_after_success(self, session, repository_factory):
        contexts = []
        manager = MagicMock(spec=DatabaseSessionManager)

        def make_context():
            contexts.append(FakeSessionContext(session))
            return contexts[-1]

        manager.get_session.side_effect = make_context

        await DocumentStatusReporter(manager, repository_factory).report(
            uuid4(), ProcessingStatus.PROCESSING
        )

        assert contexts[0].exited is True

    async def test_each_report_opens_its_own_session(self, reporter, session_manager):
        await reporter.report(uuid4(), ProcessingStatus.PROCESSING)
        await reporter.report(uuid4(), ProcessingStatus.COMPLETED)

        assert session_manager.get_session.call_count == 2


class TestErrorMessage:
    async def test_message_is_sent_for_failed(self, reporter, repository):
        await reporter.report(uuid4(), ProcessingStatus.FAILED, "extraction crashed")
        assert sent_error_message(repository) == "extraction crashed"

    @pytest.mark.parametrize(
        "status", [ProcessingStatus.PROCESSING, ProcessingStatus.COMPLETED]
    )
    async def test_message_is_dropped_for_other_statuses(
        self, reporter, repository, status
    ):
        await reporter.report(uuid4(), status, "should not be stored")
        assert sent_error_message(repository) is None

    @pytest.mark.parametrize("message", [None, ""])
    async def test_failed_without_message_sends_none(
        self, reporter, repository, message
    ):
        await reporter.report(uuid4(), ProcessingStatus.FAILED, message)
        assert sent_error_message(repository) is None

    async def test_nul_characters_are_removed(self, reporter, repository):
        await reporter.report(uuid4(), ProcessingStatus.FAILED, "bad\x00 value\x00")
        assert sent_error_message(repository) == "bad value"

    async def test_long_message_is_cut_to_the_column_limit(self, reporter, repository):
        await reporter.report(uuid4(), ProcessingStatus.FAILED, "x" * 2000)
        assert sent_error_message(repository) == "x" * MAX_CHARS

    async def test_message_at_the_limit_is_unchanged(self, reporter, repository):
        await reporter.report(uuid4(), ProcessingStatus.FAILED, "y" * MAX_CHARS)
        assert sent_error_message(repository) == "y" * MAX_CHARS

    async def test_limit_applies_after_nul_removal(self, reporter, repository):
        message = ("a\x00" * MAX_CHARS) + "b" * 10

        await reporter.report(uuid4(), ProcessingStatus.FAILED, message)

        assert sent_error_message(repository) == "a" * MAX_CHARS


class TestConflict:
    async def test_rejected_transition_raises_conflict(self, reporter, repository):
        repository.transition_document_status.return_value = False

        with pytest.raises(StatusConflict) as exc:
            await reporter.report(uuid4(), ProcessingStatus.COMPLETED)

        assert not isinstance(exc.value, StatusReportFailed)

    async def test_conflict_still_closes_the_session(
        self, session, repository, repository_factory
    ):
        contexts = []
        manager = MagicMock(spec=DatabaseSessionManager)
        manager.get_session.side_effect = (
            lambda: contexts.append(FakeSessionContext(session)) or contexts[-1]
        )
        repository.transition_document_status.return_value = False

        with pytest.raises(StatusConflict):
            await DocumentStatusReporter(manager, repository_factory).report(
                uuid4(), ProcessingStatus.PROCESSING
            )

        assert contexts[0].exited is True


class TestFailures:
    async def test_repository_error_raises_report_failed_with_cause(
        self, reporter, repository
    ):
        original = RuntimeError("db down")
        repository.transition_document_status.side_effect = original

        with pytest.raises(StatusReportFailed) as exc:
            await reporter.report(uuid4(), ProcessingStatus.PROCESSING)

        assert exc.value.__cause__ is original

    async def test_commit_error_when_the_session_closes_raises_report_failed(
        self, session, repository_factory
    ):
        manager = MagicMock(spec=DatabaseSessionManager)
        manager.get_session.side_effect = lambda: FakeSessionContext(
            session, exit_error=RuntimeError("commit failed")
        )

        with pytest.raises(StatusReportFailed):
            await DocumentStatusReporter(manager, repository_factory).report(
                uuid4(), ProcessingStatus.COMPLETED
            )

    async def test_session_open_error_raises_report_failed(
        self, session_manager, repository, repository_factory
    ):
        session_manager.get_session.side_effect = lambda: FakeSessionContext(
            None, enter_error=ConnectionError("pool exhausted")
        )

        with pytest.raises(StatusReportFailed):
            await DocumentStatusReporter(session_manager, repository_factory).report(
                uuid4(), ProcessingStatus.PROCESSING
            )

        repository.transition_document_status.assert_not_called()

    async def test_failure_is_logged(self, reporter, repository, caplog):
        repository.transition_document_status.side_effect = RuntimeError("db down")

        with caplog.at_level(logging.ERROR, logger=reporter_module.__name__):
            with pytest.raises(StatusReportFailed):
                await reporter.report(uuid4(), ProcessingStatus.PROCESSING)

        assert any(record.exc_info for record in caplog.records)

    async def test_cancellation_is_not_wrapped(self, reporter, repository):
        import asyncio

        repository.transition_document_status.side_effect = asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await reporter.report(uuid4(), ProcessingStatus.PROCESSING)
