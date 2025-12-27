"""
Local file system storage implementation.

Used for development and single-server deployments.
Stores files in a local directory structure.
"""

import shutil
from pathlib import Path
from typing import Optional, List

from src.storage.storage_base import FileStorageBase
from src.logger.base_logger import BaseLogger


class LocalFileStorage(FileStorageBase):
    """
    Local file system storage implementation.

    Structure:
        base_dir/
            sessions/
                session_123/
                    raw/
                        document.pdf
                    processed/
                        document.txt
            vectors/
                session_123_index.faiss
    """

    def __init__(self, base_dir: str = "./data/storage"):
        """
        Initialize local file storage.

        Args:
            base_dir: Root directory for file storage
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._logger = BaseLogger(__name__)

    def upload(
        self,
        file_content: bytes,
        destination_path: str,
        metadata: Optional[dict[str, str]] = None,
    ) -> str:
        """Upload file to local storage."""
        full_path = self.base_dir / destination_path

        # Create parent directories
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        full_path.write_bytes(file_content)

        self._logger.info(f"Uploaded file to {destination_path}")
        return destination_path

    def download(self, file_path: str) -> Optional[bytes]:
        """Download file from local storage."""
        full_path = self.base_dir / file_path

        if not full_path.exists():
            self._logger.warning(f"File not found: {file_path}")
            return None

        return full_path.read_bytes()

    def delete(self, entity_id: str) -> bool:
        """Delete file from local storage."""
        full_path = self.base_dir / entity_id

        if not full_path.exists():
            return False

        if full_path.is_dir():
            shutil.rmtree(full_path)
        else:
            full_path.unlink()

        self._logger.info(f"Deleted {entity_id}")
        return True

    def get_url(self, file_path: str, expiry_seconds: int = 3600) -> Optional[str]:
        """Local storage doesn't support URLs."""
        # Could return file:// URL or None
        full_path = self.base_dir / file_path
        if full_path.exists():
            return f"file://{full_path.absolute()}"
        return None

    def list_files(self, prefix: Optional[str] = None) -> List[str]:
        """List files in local storage."""
        search_path = self.base_dir / prefix if prefix else self.base_dir

        if not search_path.exists():
            return []

        files = []
        for path in search_path.rglob("*"):
            if path.is_file():
                # Return relative path
                relative = path.relative_to(self.base_dir)
                files.append(str(relative))

        return files

    def exists(self, entity_id: str) -> bool:
        """Check if file exists."""
        full_path = self.base_dir / entity_id
        return full_path.exists()
