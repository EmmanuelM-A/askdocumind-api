"""
Provides the object storage dependency. It lives apart from the uploads
dependencies so other modules can use it without importing the upload
service and its own dependencies.
"""

import boto3

from src.config.configs import settings
from src.uploads.storage.aws_s3_object_storage import AWSS3ObjectStorage
from src.uploads.storage.object_storage import ObjectStorage

_client = boto3.client(
    "s3",
    endpoint_url=settings.uploads.S3_ENDPOINT_URL,
    aws_access_key_id=settings.uploads.S3_ACCESS_KEY_ID.get_secret_value(),
    aws_secret_access_key=settings.uploads.S3_SECRET_ACCESS_KEY.get_secret_value(),
    region_name=settings.uploads.S3_REGION,
)


def get_object_storage() -> ObjectStorage:
    """
    Provide an ObjectStorage instance for the current request.
    """
    return AWSS3ObjectStorage(
        client=_client,
        bucket_name=settings.uploads.S3_BUCKET_NAME,
    )
