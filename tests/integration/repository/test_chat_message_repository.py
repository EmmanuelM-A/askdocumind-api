"""
Integration tests for Chat Message Repository.

Tests the ChatMessageRepository implementation against the
ChatMessageRepositoryInterface.
"""

import pytest
from uuid import uuid4

from src.database.models import ChatMessage
from src.database.repository.sqlalchemy import ChatMessageRepository
from src.database.repository.interfaces.chat_message_repository import (
    ChatMessageSearchCriteria,
    UpdatedChatMessageData,
)
from src.config.constants import ChatMessageRole


@pytest.fixture
async def chat_message_repo(db_connection):
    """Provide a ChatMessageRepository instance."""
    return ChatMessageRepository(connection=db_connection)


@pytest.fixture
async def cleanup_messages(db_connection):
    """Cleanup test chat messages after each test."""
    yield
    from sqlalchemy import delete

    async with db_connection.get_session() as session:
        await session.execute(delete(ChatMessage))
        await session.commit()


class TestChatMessageRepositoryCore:
    """Core CRUD functionality tests."""

    @pytest.mark.asyncio
    async def test_create_message_success(
        self, chat_message_repo, test_chat_session, cleanup_messages
    ):
        """Test successful chat message creation."""
        message = ChatMessage(
            id=uuid4(),
            session_id=test_chat_session.id,
            role=ChatMessageRole.USER,
            content="Hello, how are you?",
        )

        message_id = await chat_message_repo.create(message)

        assert message_id is not None
        assert message_id == message.id

    @pytest.mark.asyncio
    async def test_get_by_id_success(
        self, chat_message_repo, test_chat_session, cleanup_messages
    ):
        """Test retrieving a chat message by ID."""
        message = ChatMessage(
            id=uuid4(),
            session_id=test_chat_session.id,
            role=ChatMessageRole.USER,
            content="Test message",
        )
        await chat_message_repo.create(message)

        retrieved = await chat_message_repo.get_by_id(message.id)

        assert retrieved is not None
        assert retrieved.id == message.id
        assert retrieved.content == "Test message"
        assert retrieved.role == ChatMessageRole.USER

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, chat_message_repo, cleanup_messages):
        """Test retrieving non-existent message returns None."""
        fake_id = uuid4()

        result = await chat_message_repo.get_by_id(fake_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_session_id(
        self, chat_message_repo, test_chat_session, cleanup_messages
    ):
        """Test listing messages by session ID."""
        for i in range(3):
            message = ChatMessage(
                id=uuid4(),
                session_id=test_chat_session.id,
                role=ChatMessageRole.USER if i % 2 == 0 else ChatMessageRole.ASSISTANT,
                content=f"Message {i}",
            )
            await chat_message_repo.create(message)

        criteria = ChatMessageSearchCriteria(session_id=test_chat_session.id)
        results = await chat_message_repo.list_by(criteria)

        assert len(results) == 3
        assert all(m.session_id == test_chat_session.id for m in results)

    @pytest.mark.asyncio
    async def test_list_by_role(
        self, chat_message_repo, test_chat_session, cleanup_messages
    ):
        """Test filtering messages by role."""
        for i in range(2):
            await chat_message_repo.create(
                ChatMessage(
                    id=uuid4(),
                    session_id=test_chat_session.id,
                    role=ChatMessageRole.USER,
                    content=f"User message {i}",
                )
            )

        await chat_message_repo.create(
            ChatMessage(
                id=uuid4(),
                session_id=test_chat_session.id,
                role=ChatMessageRole.ASSISTANT,
                content="Assistant response",
            )
        )

        criteria = ChatMessageSearchCriteria(role=ChatMessageRole.USER)
        results = await chat_message_repo.list_by(criteria)

        assert len(results) == 2
        assert all(m.role == ChatMessageRole.USER for m in results)

    @pytest.mark.asyncio
    async def test_list_by_no_criteria(
        self, chat_message_repo, test_chat_session, cleanup_messages
    ):
        """Test listing all messages without criteria."""
        for i in range(4):
            message = ChatMessage(
                id=uuid4(),
                session_id=test_chat_session.id,
                role=ChatMessageRole.USER,
                content=f"Message {i}",
            )
            await chat_message_repo.create(message)

        results = await chat_message_repo.list_by()

        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_update_message_content(
        self, chat_message_repo, test_chat_session, cleanup_messages
    ):
        """Test updating message content."""
        message = ChatMessage(
            id=uuid4(),
            session_id=test_chat_session.id,
            role=ChatMessageRole.USER,
            content="Original content",
        )
        await chat_message_repo.create(message)

        update_data = UpdatedChatMessageData(content="Updated content")
        updated = await chat_message_repo.update(message.id, update_data)

        assert updated is not None
        assert updated.content == "Updated content"

    @pytest.mark.asyncio
    async def test_update_message_not_found(self, chat_message_repo, cleanup_messages):
        """Test updating non-existent message returns None."""
        fake_id = uuid4()
        update_data = UpdatedChatMessageData(content="New content")

        result = await chat_message_repo.update(fake_id, update_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_message_success(
        self, chat_message_repo, test_chat_session, cleanup_messages
    ):
        """Test deleting a message."""
        message = ChatMessage(
            id=uuid4(),
            session_id=test_chat_session.id,
            role=ChatMessageRole.USER,
            content="To be deleted",
        )
        await chat_message_repo.create(message)

        deleted = await chat_message_repo.delete(message.id)

        assert deleted is True

    @pytest.mark.asyncio
    async def test_delete_message_not_found(self, chat_message_repo, cleanup_messages):
        """Test deleting non-existent message returns False."""
        fake_id = uuid4()

        result = await chat_message_repo.delete(fake_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_exists_true(
        self, chat_message_repo, test_chat_session, cleanup_messages
    ):
        """Test exists returns True for existing message."""
        message = ChatMessage(
            id=uuid4(),
            session_id=test_chat_session.id,
            role=ChatMessageRole.USER,
            content="Test",
        )
        await chat_message_repo.create(message)

        exists = await chat_message_repo.exists(message.id)

        assert exists is True

    @pytest.mark.asyncio
    async def test_exists_false(self, chat_message_repo, cleanup_messages):
        """Test exists returns False for non-existent message."""
        fake_id = uuid4()

        result = await chat_message_repo.exists(fake_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_count_all(
        self, chat_message_repo, test_chat_session, cleanup_messages
    ):
        """Test counting all messages."""
        for i in range(5):
            message = ChatMessage(
                id=uuid4(),
                session_id=test_chat_session.id,
                role=ChatMessageRole.USER,
                content=f"Message {i}",
            )
            await chat_message_repo.create(message)

        count = await chat_message_repo.count()

        assert count == 5

    @pytest.mark.asyncio
    async def test_count_by_session(
        self, chat_message_repo, test_chat_session, cleanup_messages
    ):
        """Test counting messages by session."""
        for i in range(3):
            message = ChatMessage(
                id=uuid4(),
                session_id=test_chat_session.id,
                role=ChatMessageRole.USER,
                content=f"Message {i}",
            )
            await chat_message_repo.create(message)

        count = await chat_message_repo.count(filter_id=test_chat_session.id)

        assert count == 3

    @pytest.mark.asyncio
    async def test_get_by_criteria_session_and_role(
        self, chat_message_repo, test_chat_session, cleanup_messages
    ):
        """Test get_by_criteria with multiple filters."""
        message = ChatMessage(
            id=uuid4(),
            session_id=test_chat_session.id,
            role=ChatMessageRole.ASSISTANT,
            content="Assistant message",
        )
        await chat_message_repo.create(message)

        criteria = ChatMessageSearchCriteria(
            session_id=test_chat_session.id, role=ChatMessageRole.ASSISTANT
        )
        result = await chat_message_repo.get_by_criteria(criteria)

        assert result is not None
        assert result.role == ChatMessageRole.ASSISTANT

    @pytest.mark.asyncio
    async def test_delete_many_success(
        self, chat_message_repo, test_chat_session, cleanup_messages
    ):
        """Test deleting multiple messages."""
        messages = [
            ChatMessage(
                id=uuid4(),
                session_id=test_chat_session.id,
                role=ChatMessageRole.USER,
                content=f"Message {i}",
            )
            for i in range(3)
        ]
        message_ids = []
        for msg in messages:
            await chat_message_repo.create(msg)
            message_ids.append(msg.id)

        deleted_count = await chat_message_repo.delete_many(message_ids)

        assert deleted_count == 3

    @pytest.mark.asyncio
    async def test_conversation_ordering(
        self, chat_message_repo, test_chat_session, cleanup_messages
    ):
        """Test that messages maintain creation order."""
        content_list = [f"Message {i}" for i in range(5)]

        for content in content_list:
            message = ChatMessage(
                id=uuid4(),
                session_id=test_chat_session.id,
                role=ChatMessageRole.USER,
                content=content,
            )
            await chat_message_repo.create(message)

        criteria = ChatMessageSearchCriteria(session_id=test_chat_session.id)
        results = await chat_message_repo.list_by(criteria)

        assert len(results) == 5
        # Verify created_at timestamps are in order
        for i in range(len(results) - 1):
            assert results[i].created_at <= results[i + 1].created_at

    @pytest.mark.asyncio
    async def test_long_message_content(
        self, chat_message_repo, test_chat_session, cleanup_messages
    ):
        """Test storing and retrieving long message content."""
        long_content = "x" * 10000

        message = ChatMessage(
            id=uuid4(),
            session_id=test_chat_session.id,
            role=ChatMessageRole.ASSISTANT,
            content=long_content,
        )
        await chat_message_repo.create(message)

        retrieved = await chat_message_repo.get_by_id(message.id)

        assert retrieved.content == long_content
        assert len(retrieved.content) == 10000
