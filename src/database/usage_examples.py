"""
Example usage of the storage abstraction layer.

Shows how to use database and file storage in your application.
"""

from fastapi import UploadFile

from src.storage.storage_factory import StorageFactory
from src.database.models import ChatSession, Document


# ==================== DATABASE STORAGE EXAMPLE ====================


def create_chat_session(user_id: str, title: str) -> str:
    """Create a new chat session."""
    # Get storage for ChatSession model
    session_storage = StorageFactory.get_database_storage(ChatSession)

    # Create session object
    session = ChatSession(user_id=user_id, title=title, is_active=True)

    # Store in database
    session_id = session_storage.create(session)

    return session_id


def get_user_sessions(user_id: str) -> list[ChatSession]:
    """Get all sessions for a user."""
    session_storage = StorageFactory.get_database_storage(ChatSession)

    # Query by user_id
    sessions = session_storage.query({"user_id": user_id})

    return sessions


def delete_session(session_id: str) -> bool:
    """Delete a chat session."""
    session_storage = StorageFactory.get_database_storage(ChatSession)

    return session_storage.delete(session_id)


# ==================== FILE STORAGE EXAMPLE ====================


async def upload_document(session_id: str, file: UploadFile) -> tuple[str, str]:
    """
    Upload and store a document.

    Returns:
        Tuple of (document_id, file_path)
    """
    # Get storage instances
    doc_storage = StorageFactory.get_database_storage(Document)
    file_storage = StorageFactory.get_file_storage()

    # Read file content
    file_content = await file.read()

    # Create database record
    doc_metadata = Document(
        session_id=session_id,
        filename=file.filename,
        file_size=len(file_content),
        file_extension=file.filename.split(".")[-1],
        processing_status="pending",
    )

    doc_id = doc_storage.create(doc_metadata)

    # Store file
    file_path = f"sessions/{session_id}/raw/{file.filename}"
    file_storage.upload(file_content, file_path)

    # Update document record with file path
    doc_metadata.storage_path = file_path
    doc_metadata.storage_type = "local"
    doc_storage.update(doc_id, doc_metadata)

    return doc_id, file_path


def retrieve_document(document_id: str) -> bytes:
    """Retrieve a document's content."""
    # Get metadata from database
    doc_storage = StorageFactory.get_database_storage(Document)
    doc_metadata = doc_storage.get(document_id)

    if not doc_metadata or not doc_metadata.storage_path:
        raise ValueError("Document not found")

    # Download file content
    file_storage = StorageFactory.get_file_storage()
    file_content = file_storage.download(doc_metadata.storage_path)

    if not file_content:
        raise ValueError("File content not found")

    return file_content


def delete_document(document_id: str) -> bool:
    """Delete a document and its file."""
    # Get metadata
    doc_storage = StorageFactory.get_database_storage(Document)
    doc_metadata = doc_storage.get(document_id)

    if not doc_metadata:
        return False

    # Delete file if exists
    if doc_metadata.storage_path:
        file_storage = StorageFactory.get_file_storage()
        file_storage.delete(doc_metadata.storage_path)

    # Delete database record
    return doc_storage.delete(document_id)


# ==================== HYBRID APPROACH EXAMPLE ====================


async def process_and_discard_document(
    session_id: str, file: UploadFile, document_processor, embedder, vector_store
) -> str:
    """
    Process document, store embeddings, discard file.

    This is the "hybrid" approach - no file persistence.
    """
    # Get database storage only (no file storage!)
    doc_storage = StorageFactory.get_database_storage(Document)

    # Read file content
    file_content = await file.read()

    # Create metadata record
    doc_metadata = Document(
        session_id=session_id,
        filename=file.filename,
        file_size=len(file_content),
        processing_status="processing",
        storage_type="none",  # Not storing the file!
    )

    doc_id = doc_storage.create(doc_metadata)

    try:
        # Process document (in-memory, no storage)
        chunks = document_processor.process([file])

        # Generate embeddings
        vectors_and_metadata = embedder.embed_documents(chunks)

        # Store in vector store
        for vectors, metadata in vectors_and_metadata:
            vector_store.add_vectors(session_id, vectors, metadata)

        # Update status
        doc_metadata.processing_status = "completed"
        doc_metadata.chunk_count = len(list(chunks))
        doc_storage.update(doc_id, doc_metadata)

        # File is discarded (garbage collected)

        return doc_id

    except Exception as e:
        doc_metadata.processing_status = "failed"
        doc_storage.update(doc_id, doc_metadata)
        raise
