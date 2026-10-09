"""
Local file storage service for object storage ONLY TO BE USED in development.
"""

import os
import shutil
import tempfile
from pathlib import Path

from src.exceptions import object_storage_error
from src.uploads.storage.object_storage import ObjectStorage
from src.uploads.storage.utils import validate_key, normalize_prefix


class LocalFileObjectStorage(ObjectStorage):
    """
    The concrete implementation of the ObjectStorage interface that stores
    objects as files under a root directory.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as file:
                    file.write(data)
                os.replace(tmp_name, path)
            except BaseException:
                Path(tmp_name).unlink(missing_ok=True)
                raise
        except OSError as e:
            raise object_storage_error(
                message=f"Failed to save the data to the provided key'",
                error_code="SAVE_FILE_ERROR",
                cause=e,
                error_details={
                    "key": key,
                    "root": str(self._root),
                },
            ) from e

    def load(self, key: str) -> bytes | None:
        path = self._resolve(key)
        try:
            return path.read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            return None
        except OSError as e:
            raise object_storage_error(
                message=f"Failed to load the data located at the provided key",
                error_code="LOAD_FILE_ERROR",
                cause=e,
                error_details={
                    "key": key,
                    "root": str(self._root),
                },
            ) from e

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        try:
            path.unlink()
        except (FileNotFoundError, IsADirectoryError):
            raise object_storage_error(
                message=f"Failed to delete the provided key because it does "
                f"not exist or is a directory",
                error_code="DELETE_FILE_ERROR",
                error_details={
                    "key": key,
                    "root": str(self._root),
                },
            )
        except OSError as e:
            raise object_storage_error(
                message=f"Failed to delete the provided key",
                error_code="DELETE_FILE_ERROR",
                cause=e,
                error_details={
                    "key": key,
                    "root": str(self._root),
                },
            ) from e

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def delete_prefix(self, prefix: str) -> int:
        target = self._resolve(normalize_prefix(prefix))

        if not target.is_dir():
            return 0

        try:
            count = sum(1 for path in target.rglob("*") if path.is_file())
            shutil.rmtree(target)
            return count
        except OSError as e:
            raise object_storage_error(
                message=f"Failed to delete prefix '{prefix}'",
                error_code="DELETE_PREFIX_ERROR",
                cause=e,
                error_details={
                    "prefix": prefix,
                    "root": str(self._root),
                },
            ) from e

    def _resolve(self, key: str) -> Path:
        """
        Map a key to a path and confirm the path stays inside the root.
        """
        validate_key(key)

        candidate = (self._root / key).resolve()

        if not candidate.is_relative_to(self._root):
            raise ValueError(f"Key resolves outside the storage root: {key!r}")

        return candidate
