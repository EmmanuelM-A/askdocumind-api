"""
Integration tests for User Repository.

Tests the UserRepository implementation against the UserRepositoryInterface.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from src.database.models import User
from src.database.repository.sqlalchemy import UserRepository
from src.database.repository.interfaces.user_repository import UpdatedUserData


@pytest.fixture
async def user_repo(db_connection):
    """Provide a UserRepository instance."""
    return UserRepository(connection=db_connection)


@pytest.fixture
async def cleanup_users(db_connection):
    """Cleanup test users after each test."""
    yield
    from sqlalchemy import delete
    from src.database.models import ChatMessage, Document, ChatSession

    async with db_connection.get_session() as session:
        await session.execute(delete(ChatMessage))
        await session.execute(delete(Document))
        await session.execute(delete(ChatSession))
        await session.execute(delete(User))
        await session.commit()


class TestUserRepositoryCore:
    """Core CRUD functionality tests."""

    @pytest.mark.asyncio
    async def test_create_user_success(self, user_repo, cleanup_users):
        """Test successful user creation."""
        user = User(id=uuid4())

        user_id = await user_repo.create(user)

        assert user_id is not None
        assert user_id == user.id

    @pytest.mark.asyncio
    async def test_get_by_id_success(self, user_repo, cleanup_users):
        """Test retrieving a user by ID."""
        user = User(id=uuid4())
        await user_repo.create(user)

        retrieved = await user_repo.get_by_id(user.id)

        assert retrieved is not None
        assert retrieved.id == user.id
        assert retrieved.created_at is not None

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, user_repo, cleanup_users):
        """Test retrieving non-existent user returns None."""
        fake_id = uuid4()

        result = await user_repo.get_by_id(fake_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_user_timestamps_auto_set(self, user_repo, cleanup_users):
        """Test that user timestamps are automatically set on creation."""
        user = User(id=uuid4())
        await user_repo.create(user)

        retrieved = await user_repo.get_by_id(user.id)

        assert retrieved.created_at is not None
        assert retrieved.last_seen_at is not None
        assert isinstance(retrieved.created_at, datetime)
        assert isinstance(retrieved.last_seen_at, datetime)

    @pytest.mark.asyncio
    async def test_update_last_seen_at(self, user_repo, cleanup_users):
        """Test updating last_seen_at timestamp."""
        user = User(id=uuid4())
        await user_repo.create(user)

        new_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        update_data = UpdatedUserData(last_seen_at=new_time)
        updated = await user_repo.update(user.id, update_data)

        assert updated is not None
        assert updated.last_seen_at is not None

    @pytest.mark.asyncio
    async def test_update_expires_at(self, user_repo, cleanup_users):
        """Test updating expires_at timestamp."""
        user = User(id=uuid4())
        await user_repo.create(user)

        expire_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        update_data = UpdatedUserData(expires_at=expire_time)
        updated = await user_repo.update(user.id, update_data)

        assert updated is not None
        assert updated.expires_at is not None

    @pytest.mark.asyncio
    async def test_update_both_timestamps(self, user_repo, cleanup_users):
        """Test updating both last_seen_at and expires_at."""
        user = User(id=uuid4())
        await user_repo.create(user)

        new_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        expire_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        update_data = UpdatedUserData(last_seen_at=new_time, expires_at=expire_time)
        updated = await user_repo.update(user.id, update_data)

        assert updated is not None
        assert updated.last_seen_at is not None
        assert updated.expires_at is not None

    @pytest.mark.asyncio
    async def test_update_user_not_found(self, user_repo, cleanup_users):
        """Test updating non-existent user returns None."""
        fake_id = uuid4()
        update_data = UpdatedUserData(
            last_seen_at=datetime.now(timezone.utc).isoformat()
        )

        result = await user_repo.update(fake_id, update_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_user_success(self, user_repo, cleanup_users):
        """Test deleting a user."""
        user = User(id=uuid4())
        await user_repo.create(user)

        deleted = await user_repo.delete(user.id)

        assert deleted is True

    @pytest.mark.asyncio
    async def test_delete_user_not_found(self, user_repo, cleanup_users):
        """Test deleting non-existent user returns False."""
        fake_id = uuid4()

        result = await user_repo.delete(fake_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_exists_true(self, user_repo, cleanup_users):
        """Test exists returns True for existing user."""
        user = User(id=uuid4())
        await user_repo.create(user)

        exists = await user_repo.exists(user.id)

        assert exists is True

    @pytest.mark.asyncio
    async def test_exists_false(self, user_repo, cleanup_users):
        """Test exists returns False for non-existent user."""
        fake_id = uuid4()

        result = await user_repo.exists(fake_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_multiple_users_independent(self, user_repo, cleanup_users):
        """Test creating multiple users with independent data."""
        user_ids = [uuid4() for _ in range(3)]
        for uid in user_ids:
            user = User(id=uid)
            await user_repo.create(user)

        # Verify all exist and are independent
        for uid in user_ids:
            assert await user_repo.exists(uid)
            retrieved = await user_repo.get_by_id(uid)
            assert retrieved.id == uid

    @pytest.mark.asyncio
    async def test_update_preserves_created_at(self, user_repo, cleanup_users):
        """Test that updates preserve the original created_at timestamp."""
        user = User(id=uuid4())
        await user_repo.create(user)

        original = await user_repo.get_by_id(user.id)
        original_created_at = original.created_at

        # Update user
        update_data = UpdatedUserData(
            last_seen_at=datetime.now(timezone.utc).isoformat()
        )
        updated = await user_repo.update(user.id, update_data)

        assert updated.created_at == original_created_at
