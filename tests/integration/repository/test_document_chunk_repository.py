"""
Integration tests for Document Chunk Repository.

Tests the DocumentChunkRepository implementation against the
DocumentChunkRepositoryInterface.
"""

from uuid import uuid4

import pytest
from sqlalchemy import delete

from src.config.constants import ProcessingStatus
from src.database.connection import DatabaseConnection
from src.database.models import ChatSession, Document, DocumentChunk, User
from src.database.repository.interfaces.document_chunk_repository import (
    DocumentChunkSearchCriteria,
)
from src.database.repository.sqlalchemy.document_chunk_repository import (
    DocumentChunkRepository,
)


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db_connection():
    """Provide a real database connection for this test file only."""
    conn = DatabaseConnection()
    await conn.connect()
    yield conn
    await conn.disconnect()


@pytest.fixture
def document_chunk_repo(db_connection):
    """Provide a DocumentChunkRepository instance."""
    return DocumentChunkRepository(connection=db_connection)


@pytest.fixture
async def test_user(db_connection):
    """Create a test user for document ownership."""
    user = User(id=uuid4())
    async with db_connection.get_session() as session:
        session.add(user)
        await session.commit()

    yield user

    async with db_connection.get_session() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


@pytest.fixture
async def test_chat_session(db_connection, test_user):
    """Create a test chat session."""
    chat_session = ChatSession(id=uuid4(), user_id=test_user.id)
    async with db_connection.get_session() as session:
        session.add(chat_session)
        await session.commit()

    yield chat_session

    async with db_connection.get_session() as session:
        await session.execute(delete(ChatSession).where(ChatSession.id == chat_session.id))
        await session.commit()


@pytest.fixture
async def cleanup_document_chunks(db_connection):
    """Cleanup test chunk-related data after each test."""
    yield

    async with db_connection.get_session() as session:
        await session.execute(delete(DocumentChunk))
        await session.execute(delete(Document))
        await session.execute(delete(ChatSession))
        await session.execute(delete(User))
        await session.commit()


@pytest.fixture
async def test_document(db_connection, test_chat_session):
    """Create a test document for chunk tests."""
    document = Document(
        id=uuid4(),
        session_id=test_chat_session.id,
        filename="chunk-source.pdf",
        file_size=2048,
        processing_status=ProcessingStatus.COMPLETED,
    )

    async with db_connection.get_session() as session:
        session.add(document)
        await session.commit()

    yield document

    async with db_connection.get_session() as session:
        await session.execute(delete(Document).where(Document.id == document.id))
        await session.commit()


@pytest.fixture
def chunk_factory():
    """Factory for creating document chunks with deterministic embeddings."""

    def _create_chunk(
        document_id,
        *,
        chunk_index: int,
        chunk_text: str,
        head: tuple[float, float, float],
    ) -> DocumentChunk:
        embedding = list(head) + [0.0] * (1536 - len(head))
        return DocumentChunk(
            id=uuid4(),
            document_id=document_id,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            embedding=embedding,
        )

    return _create_chunk


async def _create_chunks(document_chunk_repo, chunks):
    ids = []
    for chunk in chunks:
        ids.append(await document_chunk_repo.create(chunk))
    return ids


class TestDocumentChunkRepositoryCore:
    """Core CRUD functionality tests."""

    async def test_create_chunk_success(
        self,
        document_chunk_repo,
        test_document,
        chunk_factory,
        cleanup_document_chunks,
    ):
        chunk = chunk_factory(
            test_document.id,
            chunk_index=0,
            chunk_text="Chunk text one",
            head=(1.0, 0.0, 0.0),
        )

        chunk_id = await document_chunk_repo.create(chunk)

        assert chunk_id is not None
        assert chunk_id == chunk.id

    async def test_get_by_id_success(
        self,
        document_chunk_repo,
        test_document,
        chunk_factory,
        cleanup_document_chunks,
    ):
        chunk = chunk_factory(
            test_document.id,
            chunk_index=1,
            chunk_text="Lookup chunk",
            head=(1.0, 0.0, 0.0),
        )
        await document_chunk_repo.create(chunk)

        retrieved = await document_chunk_repo.get_by_id(chunk.id)

        assert retrieved is not None
        assert retrieved.id == chunk.id
        assert retrieved.document_id == test_document.id
        assert retrieved.chunk_text == "Lookup chunk"

    async def test_get_by_id_not_found(self, document_chunk_repo, cleanup_document_chunks):
        result = await document_chunk_repo.get_by_id(uuid4())

        assert result is None

    async def test_list_by_no_criteria(
        self,
        document_chunk_repo,
        test_document,
        chunk_factory,
        cleanup_document_chunks,
    ):
        chunks = [
            chunk_factory(
                test_document.id,
                chunk_index=i,
                chunk_text=f"Chunk {i}",
                head=(1.0, 0.0, 0.0),
            )
            for i in range(3)
        ]
        await _create_chunks(document_chunk_repo, chunks)

        results = await document_chunk_repo.list_by()

        assert len(results) == 3

    async def test_list_by_document_id_filters_chunks(
        self,
        document_chunk_repo,
        db_connection,
        test_document,
        chunk_factory,
        cleanup_document_chunks,
    ):
        other_document = Document(
            id=uuid4(),
            session_id=test_document.session_id,
            filename="other.pdf",
            file_size=1024,
            processing_status=ProcessingStatus.COMPLETED,
        )

        async with db_connection.get_session() as session:
            session.add(other_document)
            await session.commit()

        try:
            chunks = [
                chunk_factory(
                    test_document.id,
                    chunk_index=0,
                    chunk_text="A",
                    head=(1.0, 0.0, 0.0),
                ),
                chunk_factory(
                    test_document.id,
                    chunk_index=1,
                    chunk_text="B",
                    head=(0.5, 0.5, 0.0),
                ),
                chunk_factory(
                    other_document.id,
                    chunk_index=0,
                    chunk_text="C",
                    head=(-1.0, 0.0, 0.0),
                ),
            ]
            await _create_chunks(document_chunk_repo, chunks)

            results = await document_chunk_repo.list_by_document_id(test_document.id)

            assert len(results) == 2
            assert all(chunk.document_id == test_document.id for chunk in results)
        finally:
            async with db_connection.get_session() as session:
                await session.execute(delete(Document).where(Document.id == other_document.id))
                await session.commit()

    async def test_get_by_criteria_chunk_and_document(
        self,
        document_chunk_repo,
        test_document,
        chunk_factory,
        cleanup_document_chunks,
    ):
        chunk = chunk_factory(
            test_document.id,
            chunk_index=2,
            chunk_text="Target chunk",
            head=(1.0, 0.0, 0.0),
        )
        await document_chunk_repo.create(chunk)

        criteria = DocumentChunkSearchCriteria(
            document_id=test_document.id,
            chunk_index=2,
        )
        result = await document_chunk_repo.get_by_criteria(criteria)

        assert result is not None
        assert result.id == chunk.id
        assert result.document_id == test_document.id
        assert result.chunk_index == 2

    async def test_exists_true_false(
        self,
        document_chunk_repo,
        test_document,
        chunk_factory,
        cleanup_document_chunks,
    ):
        chunk = chunk_factory(
            test_document.id,
            chunk_index=3,
            chunk_text="Existence chunk",
            head=(1.0, 0.0, 0.0),
        )
        await document_chunk_repo.create(chunk)

        assert await document_chunk_repo.exists(chunk.id) is True
        assert await document_chunk_repo.exists(uuid4()) is False

    async def test_count_all_and_by_document(
        self,
        document_chunk_repo,
        db_connection,
        test_document,
        chunk_factory,
        cleanup_document_chunks,
    ):
        other_document = Document(
            id=uuid4(),
            session_id=test_document.session_id,
            filename="count-other.pdf",
            file_size=512,
            processing_status=ProcessingStatus.COMPLETED,
        )

        async with db_connection.get_session() as session:
            session.add(other_document)
            await session.commit()

        try:
            chunks = [
                chunk_factory(
                    test_document.id,
                    chunk_index=0,
                    chunk_text="A",
                    head=(1.0, 0.0, 0.0),
                ),
                chunk_factory(
                    test_document.id,
                    chunk_index=1,
                    chunk_text="B",
                    head=(0.5, 0.5, 0.0),
                ),
                chunk_factory(
                    other_document.id,
                    chunk_index=0,
                    chunk_text="C",
                    head=(-1.0, 0.0, 0.0),
                ),
            ]
            await _create_chunks(document_chunk_repo, chunks)

            assert await document_chunk_repo.count() == 3
            assert await document_chunk_repo.count(document_id=test_document.id) == 2
        finally:
            async with db_connection.get_session() as session:
                await session.execute(delete(Document).where(Document.id == other_document.id))
                await session.commit()

    async def test_delete_success_and_not_found(
        self,
        document_chunk_repo,
        test_document,
        chunk_factory,
        cleanup_document_chunks,
    ):
        chunk = chunk_factory(
            test_document.id,
            chunk_index=4,
            chunk_text="Delete me",
            head=(1.0, 0.0, 0.0),
        )
        await document_chunk_repo.create(chunk)

        deleted = await document_chunk_repo.delete(chunk.id)
        missing = await document_chunk_repo.delete(uuid4())

        assert deleted is True
        assert missing is False

    async def test_delete_by_document_id_removes_all_chunks(
        self,
        document_chunk_repo,
        test_document,
        chunk_factory,
        cleanup_document_chunks,
    ):
        chunks = [
            chunk_factory(
                test_document.id,
                chunk_index=i,
                chunk_text=f"Chunk {i}",
                head=(1.0, 0.0, 0.0),
            )
            for i in range(3)
        ]
        await _create_chunks(document_chunk_repo, chunks)

        deleted_count = await document_chunk_repo.delete_by_document_id(test_document.id)

        assert deleted_count == 3
        assert await document_chunk_repo.count(document_id=test_document.id) == 0

    async def test_upsert_many_success(
        self,
        document_chunk_repo,
        test_document,
        chunk_factory,
        cleanup_document_chunks,
    ):
        chunks = [
            chunk_factory(
                test_document.id,
                chunk_index=i,
                chunk_text=f"Chunk {i}",
                head=(1.0, 0.0, 0.0),
            )
            for i in range(2)
        ]

        created_ids = await document_chunk_repo.upsert_many(chunks)

        assert len(created_ids) == 2
        assert set(created_ids) == {chunk.id for chunk in chunks}
        assert await document_chunk_repo.count(document_id=test_document.id) == 2

    async def test_search_similar_ranks_and_filters(
        self,
        document_chunk_repo,
        test_document,
        chunk_factory,
        cleanup_document_chunks,
    ):
        chunk_a = chunk_factory(
            test_document.id,
            chunk_index=0,
            chunk_text="Best match",
            head=(1.0, 0.0, 0.0),
        )
        chunk_b = chunk_factory(
            test_document.id,
            chunk_index=1,
            chunk_text="Second match",
            head=(0.5, 0.5, 0.0),
        )
        chunk_c = chunk_factory(
            test_document.id,
            chunk_index=2,
            chunk_text="Low match",
            head=(-1.0, 0.0, 0.0),
        )
        await _create_chunks(document_chunk_repo, [chunk_a, chunk_b, chunk_c])

        results = await document_chunk_repo.search_similar(
            vector=[1.0, 0.0, 0.0] + [0.0] * 1533,
            top_k=2,
            threshold=0.6,
        )

        assert len(results) == 2
        assert results[0].id == chunk_a.id
        assert results[1].id == chunk_b.id



