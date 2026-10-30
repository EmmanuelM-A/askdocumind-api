from fastapi import UploadFile
from pydantic import Field

from src.shared.utils import CamelCaseSerializer


class UploadFileRequest(CamelCaseSerializer):
    file: UploadFile = Field(description="The file to be uploaded.")
