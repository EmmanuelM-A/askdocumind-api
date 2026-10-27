"""
Integration tests for IngestionRunner.

The runner commits through its own sessions, so every row here is really
committed and removed afterwards. Extraction, chunking, status reporting and
S3 are real. Only the embedder is faked, because it calls a paid external API.
"""

import asyncio
import hashlib
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from src.config.configs import settings
from src.rag.models.chunk_embedding import ChunkEmbedding
from src.rag.services.chunk.factory import ChunkerBuildConfig, ChunkerFactory
from src.rag.services.embed.embedder import Embedder
from src.rag.services.extract.extraction import Extraction
from src.rag.services.extract.extractors.factory import ExtractorFactory
from src.rag.services.extract.file_downloader import S3FileDownloader
from src.rag.services.report.document_status_reporter import DocumentStatusReporter
from src.rag.services.utils import RunGuard
from src.uploads.domain.document import DocumentStatus
from src.uploads.models.document import Document
from src.uploads.repository.document_repository_impl import DocumentRepositoryImpl
from src.uploads.services.ingestion_service import IngestionRunner, build_job

pytestmark = pytest.mark.asyncio

DIMENSIONS = settings.rag.EMBEDDING_DIMENSIONS
TEXT = " ".join(
    f"Sentence number {i} describes the rebel fleet gathering near the moon."
    for i in range(40)
).encode()


class FakeEmbedder(Embedder):
    def __init__(self, before_embed=None, wrong_count=False):
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self._before_embed = before_embed
        self._wrong_count = wrong_count

    async def embed_chunks(self, chunks):
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self._before_embed is not None:
                await self._before_embed()
            count = len(chunks) + 1 if self._wrong_count else len(chunks)
            return [[0.1] * DIMENSIONS for _ in range(count)]
        finally:
            self.active -= 1

    async def embed_query(self, query):
        return [0.1] * DIMENSIONS


async def _failing():
    raise RuntimeError("embedding provider is down")


@pytest.fixture
def guard():
    return RunGuard()


@pytest_asyncio.fixture
async def make_runner(manager, object_storage, guard):
    runners = []

    def _make(embedder, max_concurrent=1):
        runner = IngestionRunner(
            session_manager=manager,
            extraction=Extraction(S3FileDownloader(object_storage), ExtractorFactory()),
            chunker_factory=ChunkerFactory(ChunkerBuildConfig()),
            embedder=embedder,
            status_reporter=DocumentStatusReporter(manager, DocumentRepositoryImpl),
            guard=guard,
            max_concurrent=max_concurrent,
        )
        runners.append(runner)
        return runner

    yield _make

    for runner in runners:
        await runner.shutdown()


@pytest_asyncio.fixture
async def make_document(manager, object_storage, new_chat_session):
    async def _make(
        content=TEXT,
        filename="notes.txt",
        status=DocumentStatus.UPLOADED,
        checksum=None,
        chat_session_id=None,
    ):
        chat_session_id = chat_session_id or await new_chat_session()
        key = f"{chat_session_id}/{uuid.uuid4()}"
        object_storage.save(key, content)
        async with manager.get_session() as session:
            document = Document(
                chat_session_id=chat_session_id,
                original_filename=filename,
                object_key=key,
                content_type="text/plain",
                size_bytes=len(content),
                checksum=checksum or hashlib.sha256(content).hexdigest(),
                status=status,
            )
            session.add(document)
            await session.flush()
        return document

    return _make


async def _status(manager, document_id):
    async with manager.get_session() as session:
        result = await session.execute(
            select(Document.status).where(Document.id == document_id)
        )
        return result.scalar_one()


async def _chunk_count(manager, document_id):
    async with manager.get_session() as session:
        result = await session.execute(
            select(func.count())
            .select_from(ChunkEmbedding)
            .where(ChunkEmbedding.document_id == document_id)
        )
        return result.scalar_one()


async def _ingest(runner, *documents):
    for document in documents:
        runner.start(build_job(document))
    await asyncio.gather(*list(runner._tasks))


async def test_build_job_copies_document_fields(make_document):
    document = await make_document()

    job = build_job(document)

    assert job.document_id == document.id
    assert job.chat_session_id == document.chat_session_id
    assert job.filename == document.original_filename
    assert job.content_type == document.content_type
    assert job.checksum == document.checksum
    assert job.object_key == document.object_key


async def test_max_concurrent_below_one_is_rejected(manager, object_storage, guard):
    with pytest.raises(ValueError):
        IngestionRunner(
            session_manager=manager,
            extraction=Extraction(S3FileDownloader(object_storage), ExtractorFactory()),
            chunker_factory=ChunkerFactory(ChunkerBuildConfig()),
            embedder=FakeEmbedder(),
            status_reporter=DocumentStatusReporter(manager, DocumentRepositoryImpl),
            guard=guard,
            max_concurrent=0,
        )


async def test_successful_ingestion_stores_chunks_and_completes(
    manager, make_runner, make_document
):
    embedder = FakeEmbedder()
    document = await make_document()

    await _ingest(make_runner(embedder), document)

    assert await _status(manager, document.id) == DocumentStatus.COMPLETED
    assert await _chunk_count(manager, document.id) > 0
    assert embedder.calls > 0


@pytest.mark.parametrize(
    "case",
    ["checksum-mismatch", "unsupported-extension", "no-text", "embedder-error"],
)
async def test_failed_ingestion_marks_document_failed_without_chunks(
    manager, make_runner, make_document, case
):
    embedder = FakeEmbedder(before_embed=_failing if case == "embedder-error" else None)
    overrides = {
        "checksum-mismatch": {"checksum": "0" * 64},
        "unsupported-extension": {"filename": "notes.xyz"},
        "no-text": {"content": b"   \n\n   "},
        "embedder-error": {},
    }[case]
    document = await make_document(**overrides)

    await _ingest(make_runner(embedder), document)

    assert await _status(manager, document.id) == DocumentStatus.FAILED
    assert await _chunk_count(manager, document.id) == 0


async def test_wrong_embedding_count_fails_document(
    manager, make_runner, make_document
):
    document = await make_document()

    await _ingest(make_runner(FakeEmbedder(wrong_count=True)), document)

    assert await _status(manager, document.id) == DocumentStatus.FAILED
    assert await _chunk_count(manager, document.id) == 0


@pytest.mark.parametrize(
    "status",
    [DocumentStatus.PENDING, DocumentStatus.PROCESSING, DocumentStatus.COMPLETED],
)
async def test_document_not_uploaded_is_skipped(
    manager, make_runner, make_document, status
):
    embedder = FakeEmbedder()
    document = await make_document(status=status)

    await _ingest(make_runner(embedder), document)

    assert embedder.calls == 0
    assert await _status(manager, document.id) == status


async def test_document_already_running_is_skipped(
    manager, make_runner, make_document, guard
):
    embedder = FakeEmbedder()
    document = await make_document()
    guard.acquire(document.id)

    await _ingest(make_runner(embedder), document)

    assert embedder.calls == 0
    assert await _status(manager, document.id) == DocumentStatus.UPLOADED


async def test_guard_is_released_after_a_run(make_runner, make_document, guard):
    document = await make_document(content=b"   ")

    await _ingest(make_runner(FakeEmbedder()), document)

    assert guard.acquire(document.id) is True


async def test_status_change_during_run_removes_chunks(
    manager, make_runner, make_document
):
    document = await make_document()

    async def fail_document_elsewhere():
        async with manager.get_session() as session:
            await DocumentRepositoryImpl(session).update_document_status(
                document.id, DocumentStatus.FAILED, "failed by the sweeper"
            )

    await _ingest(
        make_runner(FakeEmbedder(before_embed=fail_document_elsewhere)), document
    )

    assert await _status(manager, document.id) == DocumentStatus.FAILED
    assert await _chunk_count(manager, document.id) == 0


async def test_runs_never_exceed_max_concurrent(
    manager, make_runner, make_document, new_chat_session
):
    chat_session_id = await new_chat_session()
    embedder = FakeEmbedder(before_embed=lambda: asyncio.sleep(0.05))
    documents = [
        await make_document(filename=f"{i}.txt", chat_session_id=chat_session_id)
        for i in range(3)
    ]

    await _ingest(make_runner(embedder, max_concurrent=1), *documents)

    assert embedder.max_active == 1
    assert embedder.calls >= 3


async def test_shutdown_cancels_running_ingestions(
    manager, make_runner, make_document, guard
):
    entered, release = asyncio.Event(), asyncio.Event()

    async def block():
        entered.set()
        await release.wait()

    document = await make_document()
    runner = make_runner(FakeEmbedder(before_embed=block))
    runner.start(build_job(document))
    await asyncio.wait_for(entered.wait(), timeout=10)

    await asyncio.wait_for(runner.shutdown(), timeout=10)

    assert all(task.done() for task in runner._tasks)
    assert guard.acquire(document.id) is True
    assert await _chunk_count(manager, document.id) == 0
