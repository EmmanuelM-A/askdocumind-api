"""Reusable fixtures for storage integration tests."""

from pathlib import Path

import pytest

from src.database.storage.local_file_storage_service import LocalFileStorageService


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    """Create an isolated storage root for each test."""
    return tmp_path / "documents"


@pytest.fixture
def local_storage(
    monkeypatch: pytest.MonkeyPatch, storage_root: Path
) -> LocalFileStorageService:
    """Provide LocalFileStorageService bound to an isolated test directory."""
    monkeypatch.setattr(
        "src.database.storage.local_file_storage_service.settings.files.LOCAL_FILE_STORAGE_DIR",
        str(storage_root),
    )
    return LocalFileStorageService()

