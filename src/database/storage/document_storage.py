"""
Responsible for managing the storage of uploaded documents to a specified
location, either locally or remotely.
"""

import shutil
from pathlib import Path

from src.config.configs import settings
from src.database.models import Document
from src.database.storage.storage_base import StorageBase


"""
data/
    local/
        documents/
            dafoi09ds0a/
                sample_document.pdf
                sample_document.txt

        indexes/
            dafoi09ds0a.faiss
        metadata/
            dafoi09ds0a.pkl   
"""


class RemoteDocumentStorage(StorageBase[Document]):
    """
    Remote storage implementation to store uploaded documents to an external
    remote database service.
    """


class LocalDocumentStorage(StorageBase[Document]):
    """
    Local storage implementation to store uploaded documents on the filesystem.
    """

    def __init__(self):
        self.base_dir = Path(settings.files.LOCAL_FILE_STORAGE_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ========================= CRUD METHODS =========================

    async def create(self, entity: Document) -> str:
        """
        Store the provided entity's content to disk under a folder named by the
        entity id and return the entity id.
        """
        try:
            # normalize content to bytes
            file_content = entity.content
            if isinstance(file_content, str):
                file_bytes = file_content.encode("utf-8")
            else:
                raise TypeError("Unsupported content type for document")

            doc_id = str(entity.session_id)
            saved_path = self._upload(file_bytes, doc_id, entity.filename)

            # update metadata on the passed entity (not persisted here)
            entity.file_size = Path(saved_path).stat().st_size
            entity.content = ""  # avoid keeping large content in-memory/DB layer

            return doc_id

        except Exception as e:
            raise RuntimeError(f"Failed to create local document: {e}") from e

    async def get(self, entity_id: str) -> Optional[Document]:
        """
        Retrieve the first file found under the entity folder and return a
        Document instance populated with file contents and metadata.
        """
        try:
            dir_path = self.base_dir / entity_id
            if not dir_path.exists():
                return None

            # if a directory, pick the first file found; if it's a file, use it
            if dir_path.is_dir():
                files = [p for p in dir_path.iterdir() if p.is_file()]
                if not files:
                    return None
                file_path = files[0]
            else:
                file_path = dir_path

            content_bytes = file_path.read_bytes()
            try:
                content_str = content_bytes.decode("utf-8")
            except Exception:
                content_str = content_bytes.decode("utf-8", errors="ignore")

            from uuid import UUID as _UUID

            doc = Document()
            try:
                doc.id = _UUID(entity_id)
            except Exception:
                # keep raw string if not a UUID
                doc.id = entity_id  # type: ignore
            doc.filename = file_path.name
            doc.file_size = file_path.stat().st_size
            doc.content = content_str

            return doc

        except Exception as e:
            raise RuntimeError(f"Failed to read local document: {e}") from e

    async def update(self, entity_id: str, entity: Document) -> Optional[Document]:
        """
        Overwrite existing file (matched by filename) within the entity folder.
        Returns the updated entity or None if target doesn't exist.
        """
        try:
            dir_path = self.base_dir / entity_id
            if not dir_path.exists():
                return None

            # ensure folder exists
            dir_path.mkdir(parents=True, exist_ok=True)
            file_path = dir_path / entity.filename

            # normalize content
            file_content = entity.content
            if isinstance(file_content, str):
                file_bytes = file_content.encode("utf-8")
            elif isinstance(file_content, (bytes, bytearray)):
                file_bytes = bytes(file_content)
            else:
                raise TypeError("Unsupported content type for document")

            file_path.write_bytes(file_bytes)
            entity.file_size = file_path.stat().st_size
            entity.content = ""  # avoid keeping large content

            return entity

        except Exception as e:
            raise RuntimeError(f"Failed to update local document: {e}") from e

    async def delete(self, entity_id: str) -> bool:
        """
        Delete the file or directory for the given entity id.
        """
        try:
            return self._download(entity_id)
        except Exception as e:
            raise RuntimeError(f"Failed to delete local document: {e}") from e

    async def exists(self, entity_id: str) -> bool:
        return (self.base_dir / entity_id).exists()

    # ========================= HELPER METHODS =========================

    def _upload(self, file_content: bytes, chat_session_id: str, filename: str) -> str:
        """Upload file to local storage.\n\n        Stores the file under ``self.base_dir / chat_session_id / filename`` and returns the full path as a string."""
        session = self.base_dir / chat_session_id

        # Ensure chat session dir exists
        session.mkdir(parents=True, exist_ok=True)

        full_path = session / filename

        # Write file
        full_path.write_bytes(file_content)

        return str(full_path)

    def _download(self, entity_id: str) -> bool:
        """Delete file or directory from local storage."""
        full_path = self.base_dir / entity_id

        if not full_path.exists():
            return False

        if full_path.is_dir():
            shutil.rmtree(full_path)
        else:
            full_path.unlink()

        return True
