"""
AWS S3 storage for production use.
"""

from typing import TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError

from exceptions import object_storage_error

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

from src.uploads.storage.object_storage import (
    ObjectStorage,
    validate_key,
    normalize_prefix,
)

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
            raise object_storage_error(
                message="Failed to save object to S3",
                error_code="S3_OBJECT_SAVE_ERROR",
                error_details={"key": key, "bucket": self._bucket},
                cause=e,
            ) from e

    def load(self, key: str) -> bytes | None:
        validate_key(key)

        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in _MISSING_CODES:
                return None
            raise object_storage_error(
                message="Failed to load object from S3",
                error_code="S3_OBJECT_LOAD_ERROR",
                error_details={"key": key, "bucket": self._bucket},
                cause=e,
            ) from e
        except BotoCoreError as e:
            raise object_storage_error(
                message="Failed to load object from S3",
                error_code="S3_OBJECT_LOAD_ERROR",
                error_details={"key": key, "bucket": self._bucket},
                cause=e,
            ) from e

    def delete(self, key: str) -> None:
        validate_key(key)

        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (ClientError, BotoCoreError) as e:
            raise object_storage_error(
                message="Failed to delete object from S3",
                error_code="S3_OBJECT_DELETE_ERROR",
                error_details={"key": key, "bucket": self._bucket},
                cause=e,
            ) from e

    def exists(self, key: str) -> bool:
        validate_key(key)

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            flag = True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in _MISSING_CODES:
                flag = False
            else:
                raise object_storage_error(
                    message="Failed to check object existence in S3",
                    error_code="S3_OBJECT_EXISTS_ERROR",
                    error_details={"key": key, "bucket": self._bucket},
                    cause=e,
                ) from e
        except BotoCoreError as e:
            raise object_storage_error(
                message="Failed to check object existence in S3",
                error_code="S3_OBJECT_EXISTS_ERROR",
                error_details={"key": key, "bucket": self._bucket},
                cause=e,
            ) from e

        return flag

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
                    raise object_storage_error(
                        message="Failed to delete objects from S3",
                        error_code="S3_OBJECT_DELETE_ERROR",
                        error_details={"prefix": prefix, "bucket": self._bucket},
                    )
                deleted += len(objects)
        except (ClientError, BotoCoreError) as e:
            raise object_storage_error(
                message="Failed to delete prefix from S3",
                error_code="S3_PREFIX_DELETE_ERROR",
                error_details={"prefix": prefix, "bucket": self._bucket},
                cause=e,
            ) from e

        return deleted

    def presigned_url(self, key: str, expires_in_secs: int) -> str:
        validate_key(key)

        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in_secs,
            )
        except (ClientError, BotoCoreError) as e:
            raise object_storage_error(
                message="Failed to generate presigned URL for S3 object",
                error_code="S3_PRESIGNED_URL_ERROR",
                error_details={"key": key, "bucket": self._bucket},
                cause=e,
            ) from e
