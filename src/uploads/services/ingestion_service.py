from src.rag.dependencies import build_rag_storage_service
from src.rag.services.store import StorageJob, StoreChunkEmbeddingService
from src.uploads.models.document import Document

from fastapi import Request


class IngestionService:
    """
    Service class responsible for handling the ingestion of documents into
    the RAG storage system.
    """

    @staticmethod
    def build_job(document: Document) -> StorageJob:
        """
        Build a StorageJob from a Document instance.
        """
        return StorageJob(
            document_id=document.id,
            chat_session_id=document.chat_session_id,
            filename=document.original_filename,
            content_type=document.content_type,
            checksum=document.checksum,
            object_key=document.object_key,
        )

    @staticmethod
    async def run_ingestion(job: StorageJob, request: Request) -> None:
        """
        Run the ingestion process for a given StorageJob.
        """
        async with request.app.state.session_manager.get_session() as session:
            service: StoreChunkEmbeddingService = build_rag_storage_service(session)

            await service.run(job)
