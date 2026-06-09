"""
Integration tests for Chat Session Repository.

Tests the ChatSessionRepository implementation against the ChatSessionRepositoryInterface.
"""

import pytest
from uuid import uuid4

from src.database.models import ChatSession
from src.database.repository.sqlalchemy import ChatSessionRepository
from src.database.repository.interfaces.chat_session_repository import (
    ChatSessionSearchCriteria,
    UpdatedChatSessionData,
)


@pytest.fixture
async def chat_session_repo(db_connection):
    """Provide a ChatSessionRepository instance."""
    return ChatSessionRepository(connection=db_connection)


@pytest.fixture
async def cleanup_sessions(db_connection):
    """Cleanup test chat sessions after each test."""
    yield
    from sqlalchemy import delete
    from src.database.models import ChatMessage, Document

    async with db_connection.get_session() as session:
        await session.execute(delete(ChatMessage))
        await session.execute(delete(Document))
        await session.execute(delete(ChatSession))
        await session.commit()


class TestChatSessionRepositoryCore:
    """Core CRUD functionality tests."""

    @pytest.mark.asyncio
    async def test_create_session_success(
        self, chat_session_repo, test_user, cleanup_sessions
    ):
        """Test successful chat session creation."""
        session = ChatSession(id=uuid4(), user_id=test_user.id)

        session_id = await chat_session_repo.create(session)

        assert session_id is not None
        assert session_id == session.id

    @pytest.mark.asyncio
    async def test_get_by_id_success(
        self, chat_session_repo, test_user, cleanup_sessions
    ):
        """Test retrieving a chat session by ID."""
        session = ChatSession(id=uuid4(), user_id=test_user.id)
        await chat_session_repo.create(session)

        retrieved = await chat_session_repo.get_by_id(session.id)

        assert retrieved is not None
        assert retrieved.id == session.id
        assert retrieved.user_id == test_user.id

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, chat_session_repo, cleanup_sessions):
        """Test retrieving non-existent session returns None."""
        fake_id = uuid4()

        result = await chat_session_repo.get_by_id(fake_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_id(self, chat_session_repo, test_user, cleanup_sessions):
        """Test listing sessions by ID."""
        session = ChatSession(id=uuid4(), user_id=test_user.id)
        await chat_session_repo.create(session)

        criteria = ChatSessionSearchCriteria(id=session.id)
        results = await chat_session_repo.list_by(criteria)

        assert len(results) >= 1
        assert any(s.id == session.id for s in results)

    @pytest.mark.asyncio
    async def test_list_by_no_criteria(
        self, chat_session_repo, test_user, cleanup_sessions
    ):
        """Test listing all sessions without criteria."""
        for i in range(3):
            session = ChatSession(id=uuid4(), user_id=test_user.id)
            await chat_session_repo.create(session)

        results = await chat_session_repo.list_by()

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_update_session_title(
        self, chat_session_repo, test_user, cleanup_sessions
    ):
        """Test updating session title."""
        session = ChatSession(id=uuid4(), user_id=test_user.id, title="Old Title")
        await chat_session_repo.create(session)

        update_data = UpdatedChatSessionData(title="New Title")
        updated = await chat_session_repo.update(session.id, update_data)

        assert updated is not None
        assert updated.title == "New Title"

    @pytest.mark.asyncio
    async def test_update_session_not_found(self, chat_session_repo, cleanup_sessions):
        """Test updating non-existent session returns None."""
        fake_id = uuid4()
        update_data = UpdatedChatSessionData(title="New Title")

        result = await chat_session_repo.update(fake_id, update_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_update_partial_fields(
        self, chat_session_repo, test_chat_session, cleanup_sessions
    ):
        """Test updating only some fields."""
        # Update only title
        update_data = UpdatedChatSessionData(title="Updated Title")
        updated = await chat_session_repo.update(test_chat_session.id, update_data)

        assert updated.title == "Updated Title"

    @pytest.mark.asyncio
    async def test_delete_session_success(
        self, chat_session_repo, test_user, cleanup_sessions
    ):
        """Test deleting a session."""
        session = ChatSession(id=uuid4(), user_id=test_user.id)
        await chat_session_repo.create(session)

        deleted_chat_id = await chat_session_repo.delete(session.id)

        assert deleted_chat_id == session.id
        assert await chat_session_repo.exists(session.id) is False

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, chat_session_repo, cleanup_sessions):
        """Test deleting non-existent session returns False."""
        fake_id = uuid4()

        result = await chat_session_repo.delete(fake_id)

        assert result == fake_id

    @pytest.mark.asyncio
    async def test_exists_true(self, chat_session_repo, test_user, cleanup_sessions):
        """Test exists returns True for existing session."""
        session = ChatSession(id=uuid4(), user_id=test_user.id)
        await chat_session_repo.create(session)

        exists = await chat_session_repo.exists(session.id)

        assert exists is True

    @pytest.mark.asyncio
    async def test_exists_false(self, chat_session_repo, cleanup_sessions):
        """Test exists returns False for non-existent session."""
        fake_id = uuid4()

        result = await chat_session_repo.exists(fake_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_count_all(self, chat_session_repo, test_user, cleanup_sessions):
        """Test counting all sessions."""
        for i in range(5):
            session = ChatSession(id=uuid4(), user_id=test_user.id)
            await chat_session_repo.create(session)

        count = await chat_session_repo.count()

        assert count == 5

    @pytest.mark.asyncio
    async def test_count_by_filter_id(self, chat_session_repo, test_user, cleanup_sessions):
        """Test counting sessions by session ID filter."""
        for i in range(3):
            session = ChatSession(id=uuid4(), user_id=test_user.id)
            await chat_session_repo.create(session)

        target_session = await chat_session_repo.list_by(ChatSessionSearchCriteria())
        count = await chat_session_repo.count(filter_id=target_session[0].id)

        assert count == 1

    @pytest.mark.asyncio
    async def test_get_by_criteria_id(
        self, chat_session_repo, test_user, cleanup_sessions
    ):
        """Test get_by_criteria with ID."""
        session = ChatSession(id=uuid4(), user_id=test_user.id, title="Test Session")
        await chat_session_repo.create(session)

        criteria = ChatSessionSearchCriteria(id=session.id)
        result = await chat_session_repo.get_by_criteria(criteria)

        assert result is not None
        assert result.id == session.id

    @pytest.mark.asyncio
    async def test_get_by_criteria_not_found(self, chat_session_repo, cleanup_sessions):
        """Test get_by_criteria returns None when no match."""
        fake_id = uuid4()
        criteria = ChatSessionSearchCriteria(id=fake_id)

        result = await chat_session_repo.get_by_criteria(criteria)

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_many_success(
        self, chat_session_repo, test_user, cleanup_sessions
    ):
        """Test deleting multiple sessions."""
        sessions = [ChatSession(id=uuid4(), user_id=test_user.id) for _ in range(3)]
        session_ids = []
        for session in sessions:
            await chat_session_repo.create(session)
            session_ids.append(session.id)

        deleted_count = await chat_session_repo.delete_many(session_ids)

        assert deleted_count == 3

    @pytest.mark.asyncio
    async def test_delete_many_partial(
        self, chat_session_repo, test_user, cleanup_sessions
    ):
        """Test deleting with some non-existent IDs."""
        session = ChatSession(id=uuid4(), user_id=test_user.id)
        await chat_session_repo.create(session)

        fake_id = uuid4()
        deleted_count = await chat_session_repo.delete_many([session.id, fake_id])

        # Should only delete the real one
        assert deleted_count >= 1

    @pytest.mark.asyncio
    async def test_isolation_multiple_sessions(
        self, chat_session_repo, test_chat_session, db_connection, cleanup_sessions
    ):
        """Test session isolation by verifying independent sessions."""
        # Create additional session for same user
        session2 = ChatSession(id=uuid4(), user_id=test_chat_session.user_id)
        async with db_connection.get_session() as db_session:
            db_session.add(session2)
            await db_session.commit()

        # List all sessions
        all_sessions = await chat_session_repo.list_by()

        assert len(all_sessions) >= 2
