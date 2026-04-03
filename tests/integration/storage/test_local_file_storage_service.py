"""Integration tests for local file storage service operations."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.database.storage.local_file_storage_service import LocalFileStorageService

pytest_plugins = ("tests.integration.storage.fixtures",)


def test_initializes_storage_root_directory(
    local_storage: LocalFileStorageService,
    storage_root: Path,
):
    assert local_storage.root == storage_root
    assert storage_root.exists()
    assert storage_root.is_dir()


def test_save_and_load_round_trip(local_storage: LocalFileStorageService):
    key = "chat-1/Battle_of_Endor.pdf"
    payload = b"battle data"

    local_storage.save(key, payload)

    assert local_storage.load(key) == payload


def test_exists_true_for_saved_file(local_storage: LocalFileStorageService):
    key = "chat-1/Battle_of_Hoth.md"
    local_storage.save(key, b"hoth")

    assert local_storage.exists(key) is True


def test_exists_false_for_missing_file(local_storage: LocalFileStorageService):
    assert local_storage.exists("chat-1/missing.txt") is False


def test_load_missing_file_returns_none(local_storage: LocalFileStorageService):
    assert local_storage.load("chat-1/missing.txt") is None


def test_delete_existing_file_returns_path(local_storage: LocalFileStorageService):
    key = "chat-1/delete-me.txt"
    local_storage.save(key, b"x")

    deleted = local_storage.delete(key)

    assert deleted is not None
    assert local_storage.exists(key) is False


def test_delete_missing_file_returns_none(local_storage: LocalFileStorageService):
    assert local_storage.delete("chat-1/missing.txt") is None


def test_update_existing_file_overwrites_content(
    local_storage: LocalFileStorageService,
):
    key = "chat-1/update.txt"
    local_storage.save(key, b"before")

    local_storage.update(key, b"after")

    assert local_storage.load(key) == b"after"


def test_update_missing_file_raises_file_not_found(
    local_storage: LocalFileStorageService,
):
    with pytest.raises(FileNotFoundError):
        local_storage.update("chat-1/missing.txt", b"data")


def test_count_all_files(local_storage: LocalFileStorageService):
    local_storage.save("chat-a/file1.txt", b"1")
    local_storage.save("chat-b/file2.txt", b"2")
    local_storage.save("chat-b/file3.txt", b"3")

    assert local_storage.count() == 3


def test_count_for_specific_folder(local_storage: LocalFileStorageService):
    local_storage.save("chat-a/file1.txt", b"1")
    local_storage.save("chat-a/file2.txt", b"2")
    local_storage.save("chat-b/file3.txt", b"3")

    assert local_storage.count("chat-a") == 2


def test_count_for_specific_file_key(local_storage: LocalFileStorageService):
    key = "chat-a/file1.txt"
    local_storage.save(key, b"1")

    assert local_storage.count(key) == 1


def test_count_for_missing_key_returns_zero(local_storage: LocalFileStorageService):
    assert local_storage.count("chat-none") == 0


def test_delete_all_for_chat_removes_files_and_chat_folder(
    local_storage: LocalFileStorageService,
):
    chat_id = "876e9c45-b84d-416d-a9bf-0ef3e6dee81d"
    local_storage.save(f"{chat_id}/Battle_of_Endor.pdf", b"pdf-bytes")
    local_storage.save(f"{chat_id}/Battle_of_Hoth.md", b"md-bytes")

    chat_folder = local_storage.root / chat_id
    assert chat_folder.exists()

    deleted_count = local_storage.delete_all(chat_id)

    assert deleted_count == 2
    assert not chat_folder.exists()


def test_delete_all_for_single_file_key(local_storage: LocalFileStorageService):
    key = "chat-1/file.txt"
    local_storage.save(key, b"data")

    deleted_count = local_storage.delete_all(key)

    assert deleted_count == 1
    assert local_storage.exists(key) is False


def test_delete_all_for_missing_key_returns_zero(
    local_storage: LocalFileStorageService,
):
    assert local_storage.delete_all("chat-x") == 0


def test_delete_all_without_key_clears_all_files(
    local_storage: LocalFileStorageService,
):
    local_storage.save("chat-a/file-a.txt", b"a")
    local_storage.save("chat-b/file-b.txt", b"b")

    deleted_count = local_storage.delete_all()

    assert deleted_count == 2
    assert local_storage.count() == 0
    assert local_storage.root.exists()


def test_save_rejects_path_traversal(local_storage: LocalFileStorageService):
    with pytest.raises(ValueError):
        local_storage.save("../outside.txt", b"x")


def test_load_rejects_path_traversal(local_storage: LocalFileStorageService):
    with pytest.raises(ValueError):
        local_storage.load("../../outside.txt")


def test_delete_all_rejects_path_traversal(local_storage: LocalFileStorageService):
    with pytest.raises(ValueError):
        local_storage.delete_all("../outside")


def test_save_wraps_ioerror_when_open_fails(local_storage: LocalFileStorageService):
    with patch("builtins.open", side_effect=OSError("disk full")):
        with pytest.raises(IOError):
            local_storage.save("chat-1/file.txt", b"data")


def test_load_wraps_ioerror_when_open_fails(local_storage: LocalFileStorageService):
    key = "chat-1/file.txt"
    local_storage.save(key, b"data")

    with patch("builtins.open", side_effect=OSError("read failed")):
        with pytest.raises(IOError):
            local_storage.load(key)


def test_update_wraps_ioerror_when_open_fails(local_storage: LocalFileStorageService):
    key = "chat-1/file.txt"
    local_storage.save(key, b"data")

    with patch("builtins.open", side_effect=OSError("write failed")):
        with pytest.raises(IOError):
            local_storage.update(key, b"new-data")
