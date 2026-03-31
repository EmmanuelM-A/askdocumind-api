"""
Local file storage service.

Stores raw bytes under a configurable root directory. Keys are treated as
paths relative to the root; path traversal outside the root is rejected.
"""

from pathlib import Path

from src.config.configs import settings
from src.database.storage.storage_service import StorageService


class LocalFileStorageService(StorageService):
    """
    Local file storage service implementation.
    """

    def __init__(self):
        """Initialize local file storage service."""

        self.root = Path(settings.files.LOCAL_FILE_STORAGE_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, data: bytes) -> None:
        """
        Save data to a local file under the given key.

        :param key: The key (path relative to root) to save the data under.
        :param data: The raw bytes to save.

        :raise IOError: If saving fails.
        """

        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, "wb") as f:
                f.write(data)
        except Exception as e:
            raise IOError(f"Failed to save data to {key}: {e}") from e

    def load(self, key: str) -> bytes | None:
        """
        Load data from a local file under the given key.

        :param key: The key (path relative to root) to load the data from.
        :return: The raw bytes if the file exists, None otherwise.

        :raise IOError: If loading fails.
        """

        path = self._resolve(key)

        if not path.is_file():
            return None

        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception as e:
            raise IOError(f"Failed to load data from {key}: {e}") from e

    def delete(self, key: str) -> str | None:
        """
        Delete the file under the given key.

        :param key: The key (path relative to root) of the file to delete.
        :return: The path of the deleted file as a string if it existed, None otherwise.

        :raise IOError: If deletion fails.
        """

        path = self._resolve(key)
        try:
            if path.is_file():
                path.unlink()
                return path.as_posix()

            return None
        except FileNotFoundError:
            return None

    def exists(self, key: str) -> bool:
        """
        Check if a file exists under the given key.

        :param key: The key (path relative to root) to check for existence.
        :return: True if the file exists, False otherwise.
        """

        path = self._resolve(key)
        return path.exists()

    def update(self, key: str, new_data: bytes) -> None:
        """
        Update the data of an existing file under the given key.

        :param key: The key (path relative to root) of the file to update.
        :param new_data: The new raw bytes to write to the file.
        :return: The updated data as raw bytes.

        :raise FileNotFoundError: If the file does not exist.
        :raise IOError: If updating fails.
        """

        path = self._resolve(key)

        if not path.exists():
            raise FileNotFoundError(f"Cannot update non-existent key: {key}")

        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, "wb") as f:
                f.write(new_data)
        except Exception as e:
            raise IOError(f"Failed to update data at {key}: {e}") from e

    def count(self, key: str = None) -> int:
        """
        Count the number of files stored under the given key (or root if no key).

        :param key: The key (path relative to root) to count files under.
        :return: The number of files found.
        """

        target = self._resolve(key) if key else self.root.resolve()

        if target.is_file():
            return 1 if target.exists() else 0

        if not target.exists():
            return 0

        # count files recursively
        return sum(1 for _ in target.rglob("*") if _.is_file())

    def delete_all(self, key: str | None = None) -> int:
        """
        Delete all files under the given key scope.

        :param key: Optional key (path relative to root). If None, delete all files under root.
        :return: Number of deleted files.

        :raise IOError: If bulk deletion fails.
        """

        target = self._resolve(key) if key else self.root.resolve()

        if not target.exists():
            return 0

        deleted_count = 0

        try:
            if target.is_file():
                target.unlink()
                return 1

            files = [path for path in target.rglob("*") if path.is_file()]
            for file_path in files:
                file_path.unlink()
                deleted_count += 1

            # Remove empty directories from deepest to shallowest, but never remove root.
            dirs = sorted(
                [path for path in target.rglob("*") if path.is_dir()],
                key=lambda p: len(p.parts),
                reverse=True,
            )
            for dir_path in dirs:
                if dir_path != self.root.resolve():
                    try:
                        dir_path.rmdir()
                    except OSError:
                        # Directory not empty (or in use), keep going.
                        pass

            return deleted_count
        except Exception as e:
            raise IOError(f"Failed to delete all data under {key or '/'}: {e}") from e

    # ============================ HELPER METHODS ============================

    def _resolve(self, key: str) -> Path:
        """
        Resolve the full path for a given key within the storage root.

        :param key: The key (path relative to root).
        :return: The resolved Path object.

        :raises ValueError: If the resolved path is outside the storage root.
        """

        candidate = (self.root / key).resolve()
        root_resolved = self.root.resolve()

        if not str(candidate).startswith(str(root_resolved)):
            raise ValueError("Key resolves outside of storage root")

        return candidate
