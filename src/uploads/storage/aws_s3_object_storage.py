"""
AWS S3 storage for production use.
"""

from typing import TYPE_CHECKING

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from src.uploads.storage.utils import validate_key

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

from src.config.configs import settings
from src.uploads.storage.object_storage import ObjectStorage

_MISSING_CODES = {"NoSuchKey", "404", "NotFound"}


class AWSS3ObjectStorage(ObjectStorage):
    """
    The concrete implementation of the ObjectStorage interface that uses AWS
    S3 for object storage.
    """

    def __init__(self, client: "S3Client", bucket_name: str) -> None:
        self._bucket = bucket_name
        self._client = client

    def save(self, key: str, data: bytes) -> None:
        validate_key(key)
        try:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        except (ClientError, BotoCoreError) as e:
            raise StorageError(f"Failed to save '{key}'") from e

    def load(self, key: str) -> bytes | None:
        validate_key(key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in _MISSING_CODES:
                return None
            raise StorageError(f"Failed to load '{key}'") from e
        except BotoCoreError as e:
            raise StorageError(f"Failed to load '{key}'") from e

    def delete(self, key: str) -> None:
        validate_key(key)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (ClientError, BotoCoreError) as e:
            raise StorageError(f"Failed to delete '{key}'") from e

    def exists(self, key: str) -> bool:
        validate_key(key)
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in _MISSING_CODES:
                return False
            raise StorageError(f"Failed to check '{key}'") from e
        except BotoCoreError as e:
            raise StorageError(f"Failed to check '{key}'") from e

    def delete_prefix(self, prefix: str) -> int:
        scope = normalize_prefix(prefix) + "/"
        deleted = 0
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=scope):
                objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                if not objects:
                    continue
                response = self._client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": objects, "Quiet": True},
                )
                failed = response.get("Errors", [])
                if failed:
                    raise StorageError(
                        f"Failed to delete {len(failed)} objects under '{scope}'"
                    )
                deleted += len(objects)
        except (ClientError, BotoCoreError) as e:
            raise StorageError(f"Failed to delete prefix '{prefix}'") from e
        return deleted
