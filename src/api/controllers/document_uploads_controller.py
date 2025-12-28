"""
Controller layer responsible for handling document uploads.
Handles application logic related to document uploads and interactions with the
service layer.
"""

from src.services.document_uploads import UploadService


class DocumentUploadController:
    """
    Orchestrates document upload requests between API and service layers.
    """

    def __init__(self):
        self.upload_service = UploadService()

    async def upload_files_endpoint(self):
        pass

    async def list_uploaded_files_endpoint(self):
        pass
