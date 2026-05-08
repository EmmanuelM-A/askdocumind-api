"""
Integration tests for Document Repository.

Tests the DocumentRepository implementation against the DocumentRepositoryInterface.
Can be reused for other implementations by changing the repository instantiation.
"""

import pytest
from uuid import uuid4

from src.database.models import Document, ChatSession
from src.database.repository.sqlalchemy import DocumentRepository
from src.database.repository.interfaces.document_repository import (
    DocumentSearchCriteria,
    UpdatedDocumentData,
)
from src.config.constants import ProcessingStatus


@pytest.fixture
async def document_repo(db_connection):
    """Provide a DocumentRepository instance."""
    return DocumentRepository(connection=db_connection)


@pytest.fixture
async def cleanup_documents(db_connection):
    """Cleanup test documents after each test."""
    yield
    from sqlalchemy import delete

    async with db_connection.get_session() as session:
        await session.execute(delete(Document))
        await session.execute(delete(ChatSession))
        await session.commit()


class TestDocumentRepositoryCore:
    """Core CRUD functionality tests."""

    @pytest.mark.asyncio
    async def test_create_document_success(
        self, document_repo, cleanup_documents, test_chat_session
    ):
        """Test successful document creation."""
        doc = Document(
            id=uuid4(),
            session_id=test_chat_session.id,
            filename="test.pdf",
            file_size=123,
            processing_status=ProcessingStatus.PENDING,
        )

        doc_id = await document_repo.create(doc)

        assert doc_id is not None
        assert doc_id == doc.id

    @pytest.mark.asyncio
    async def test_create_document_multiple(
        self, document_repo, test_chat_session, cleanup_documents
    ):
        """Test creating multiple documents in sequence."""
        docs = [
            Document(
                id=uuid4(),
                session_id=test_chat_session.id,
                filename=f"doc{i}.pdf",
                file_size=123,
            )
            for i in range(3)
        ]

        ids = []
        for doc in docs:
            doc_id = await document_repo.create(doc)
            ids.append(doc_id)

        assert len(ids) == 3
        assert len(set(ids)) == 3

    @pytest.mark.asyncio
    async def test_get_by_id_success(
        self, document_repo, test_chat_session, cleanup_documents
    ):
        """Test retrieving a document by ID."""
        doc = Document(
            id=uuid4(),
            session_id=test_chat_session.id,
            filename="test.pdf",
            file_size=123,
        )
        await document_repo.create(doc)

        retrieved = await document_repo.get_by_id(doc.id)

        assert retrieved is not None
        assert retrieved.id == doc.id
        assert retrieved.filename == "test.pdf"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, document_repo, cleanup_documents):
        """Test retrieving non-existent document returns None."""
        fake_id = uuid4()

        result = await document_repo.get_by_id(fake_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_no_criteria(
        self, document_repo, test_chat_session, cleanup_documents
    ):
        """Test listing all documents without criteria."""
        docs = [
            Document(
                id=uuid4(),
                session_id=test_chat_session.id,
                filename=f"doc{i}.pdf",
                file_size=123,
            )
            for i in range(3)
        ]
        for doc in docs:
            await document_repo.create(doc)

        results = await document_repo.list_by()

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_list_by_session_id(
        self, document_repo, test_chat_session, db_connection, cleanup_documents
    ):
        """Test filtering documents by session ID."""
        # Create docs in test session
        for i in range(2):
            doc = Document(
                id=uuid4(),
                session_id=test_chat_session.id,
                filename=f"doc{i}.pdf",
                file_size=123,
            )
            await document_repo.create(doc)

        # Create another session and doc
        other_session = ChatSession(id=uuid4(), user_id=test_chat_session.user_id)
        async with db_connection.get_session() as session:
            session.add(other_session)
            await session.commit()

        other_doc = Document(
            id=uuid4(), session_id=other_session.id, filename="other.pdf", file_size=123
        )
        await document_repo.create(other_doc)

        criteria = DocumentSearchCriteria(session_id=test_chat_session.id)
        results = await document_repo.list_by(criteria)

        assert len(results) == 2
        assert all(d.chat_session_id == test_chat_session.id for d in results)

    @pytest.mark.asyncio
    async def test_list_by_processing_status(
        self, document_repo, test_chat_session, cleanup_documents
    ):
        """Test filtering by processing status."""
        doc_pending = Document(
            id=uuid4(),
            session_id=test_chat_session.id,
            filename="pending.pdf",
            file_size=123,
            processing_status=ProcessingStatus.PENDING,
        )
        doc_completed = Document(
            id=uuid4(),
            session_id=test_chat_session.id,
            filename="completed.pdf",
            file_size=123,
            processing_status=ProcessingStatus.COMPLETED,
        )
        await document_repo.create(doc_pending)
        await document_repo.create(doc_completed)

        criteria = DocumentSearchCriteria(processing_status=ProcessingStatus.COMPLETED)
        results = await document_repo.list_by(criteria)

        assert len(results) == 1
        assert results[0].processing_status == ProcessingStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_update_document_success(
        self, document_repo, test_chat_session, cleanup_documents
    ):
        """Test updating a document."""
        doc = Document(
            id=uuid4(),
            session_id=test_chat_session.id,
            filename="original.pdf",
            file_size=123,
            processing_status=ProcessingStatus.PENDING,
        )
        await document_repo.create(doc)

        update_data = UpdatedDocumentData(
            filename="updated.pdf",
            processing_status=ProcessingStatus.COMPLETED,
        )
        updated = await document_repo.update(doc.id, update_data)

        assert updated is not None
        assert updated.filename == "updated.pdf"
        assert updated.processing_status == ProcessingStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_update_document_not_found(self, document_repo, cleanup_documents):
        """Test updating non-existent document returns None."""
        fake_id = uuid4()
        update_data = UpdatedDocumentData(filename="new.pdf")

        result = await document_repo.update(fake_id, update_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_update_partial_fields(
        self, document_repo, test_chat_session, cleanup_documents
    ):
        """Test updating only some fields."""
        doc = Document(
            id=uuid4(),
            session_id=test_chat_session.id,
            filename="test.pdf",
            file_size=123,
            processing_status=ProcessingStatus.PENDING,
        )
        await document_repo.create(doc)

        # Update only filename
        update_data = UpdatedDocumentData(filename="new_name.pdf")
        updated = await document_repo.update(doc.id, update_data)

        assert updated.filename == "new_name.pdf"
        assert updated.processing_status == ProcessingStatus.PENDING

    @pytest.mark.asyncio
    async def test_delete_document_success(
        self, document_repo, test_chat_session, cleanup_documents
    ):
        """Test deleting a document."""
        doc = Document(
            id=uuid4(),
            session_id=test_chat_session.id,
            filename="test.pdf",
            file_size=123,
        )
        await document_repo.create(doc)

        deleted = await document_repo.delete(doc.id)

        assert deleted is True

    @pytest.mark.asyncio
    async def test_delete_document_not_found(self, document_repo, cleanup_documents):
        """Test deleting non-existent document returns False."""
        fake_id = uuid4()

        result = await document_repo.delete(fake_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_exists_true(
        self, document_repo, test_chat_session, cleanup_documents
    ):
        """Test exists returns True for existing document."""
        doc = Document(
            id=uuid4(),
            session_id=test_chat_session.id,
            filename="test.pdf",
            file_size=123,
        )
        await document_repo.create(doc)

        exists = await document_repo.exists(doc.id)

        assert exists is True

    @pytest.mark.asyncio
    async def test_exists_false(self, document_repo, cleanup_documents):
        """Test exists returns False for non-existent document."""
        fake_id = uuid4()

        result = await document_repo.exists(fake_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_count_all(self, document_repo, test_chat_session, cleanup_documents):
        """Test counting all documents."""
        for i in range(5):
            doc = Document(
                id=uuid4(),
                session_id=test_chat_session.id,
                filename=f"doc{i}.pdf",
                file_size=123,
            )
            await document_repo.create(doc)

        count = await document_repo.count()

        assert count == 5

    @pytest.mark.asyncio
    async def test_count_by_session(
        self, document_repo, test_chat_session, cleanup_documents
    ):
        """Test counting documents by session."""
        for i in range(3):
            doc = Document(
                id=uuid4(),
                session_id=test_chat_session.id,
                filename=f"doc{i}.pdf",
                file_size=123,
            )
            await document_repo.create(doc)

        count = await document_repo.count(filter_id=test_chat_session.id)

        assert count == 3

    @pytest.mark.asyncio
    async def test_get_by_criteria_success(
        self, document_repo, test_chat_session, cleanup_documents
    ):
        """Test get_by_criteria returns first match."""
        doc = Document(
            id=uuid4(),
            session_id=test_chat_session.id,
            filename="unique.pdf",
            file_size=123,
            processing_status=ProcessingStatus.COMPLETED,
        )
        await document_repo.create(doc)

        criteria = DocumentSearchCriteria(filename="unique.pdf")
        result = await document_repo.get_by_criteria(criteria)

        assert result is not None
        assert result.filename == "unique.pdf"

    @pytest.mark.asyncio
    async def test_get_by_criteria_not_found(self, document_repo, cleanup_documents):
        """Test get_by_criteria returns None when no match."""
        criteria = DocumentSearchCriteria(filename="nonexistent.pdf")

        result = await document_repo.get_by_criteria(criteria)

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_many_success(
        self, document_repo, test_chat_session, cleanup_documents
    ):
        """Test deleting multiple documents."""
        docs = [
            Document(
                id=uuid4(),
                session_id=test_chat_session.id,
                filename=f"doc{i}.pdf",
                file_size=123,
            )
            for i in range(3)
        ]
        doc_ids = []
        for doc in docs:
            await document_repo.create(doc)
            doc_ids.append(doc.id)

        deleted_count = await document_repo.delete_many(doc_ids)

        assert deleted_count == 3

    @pytest.mark.asyncio
    async def test_bulk_update_processing_status(
        self, document_repo, test_chat_session, cleanup_documents
    ):
        """Test bulk updating processing status."""
        docs = [
            Document(
                id=uuid4(),
                session_id=test_chat_session.id,
                filename=f"doc{i}.pdf",
                file_size=123,
                processing_status=ProcessingStatus.PENDING,
            )
            for i in range(3)
        ]
        doc_ids = []
        for doc in docs:
            await document_repo.create(doc)
            doc_ids.append(doc.id)

        updated_count = await document_repo.bulk_update_processing_status(
            doc_ids, ProcessingStatus.COMPLETED
        )

        assert updated_count == 3

        # Verify updates
        results = await document_repo.list_by()
        assert all(d.processing_status == ProcessingStatus.COMPLETED for d in results)
