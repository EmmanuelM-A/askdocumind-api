"""
AWS S3 storage for production use.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError

from src.exceptions import ApiException, object_storage_error, service_unavailable_error

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

from src.uploads.storage.object_storage import (
    ObjectStorage,
    normalize_prefix,
    validate_key,
)

_MISSING_CODES = {"NoSuchKey", "404", "NotFound"}


def _is_outage(error: Exception) -> bool:
    if isinstance(error, BotoCoreError):
        return True
    if isinstance(error, ClientError):
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return isinstance(status, int) and status >= 500
    return False


def _storage_error(
    message: str, error_code: str, error_details: dict[str, str], cause: Exception
) -> ApiException:
    # Unreachable or failing storage is a 503 the client can retry. Anything
    # else (bad credentials, missing bucket) is a server bug or misconfig.
    factory = service_unavailable_error if _is_outage(cause) else object_storage_error
    return factory(
        message=message,
        error_code=error_code,
        error_details=error_details,
        cause=cause,
    )


class AWSS3ObjectStorage(ObjectStorage):
    """
    The concrete implementation of the ObjectStorage interface that uses AWS
    S3 for object storage.
    """

    def __init__(self, client: "S3Client", bucket_name: str) -> None:
        self._bucket = bucket_name
        self._client = client

    def check_available(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except (ClientError, BotoCoreError) as e:
            raise _storage_error(
                message="The S3 bucket is not reachable",
                error_code="S3_BUCKET_UNAVAILABLE",
                error_details={"bucket": self._bucket},
                cause=e,
            ) from e

    def save(self, key: str, data: bytes) -> None:
        validate_key(key)

        try:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        except (ClientError, BotoCoreError) as e:
            raise _storage_error(
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
            raise _storage_error(
                message="Failed to load object from S3",
                error_code="S3_OBJECT_LOAD_ERROR",
                error_details={"key": key, "bucket": self._bucket},
                cause=e,
            ) from e
        except BotoCoreError as e:
            raise _storage_error(
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
            raise _storage_error(
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
                raise _storage_error(
                    message="Failed to check object existence in S3",
                    error_code="S3_OBJECT_EXISTS_ERROR",
                    error_details={"key": key, "bucket": self._bucket},
                    cause=e,
                ) from e
        except BotoCoreError as e:
            raise _storage_error(
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
            raise _storage_error(
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
            raise _storage_error(
                message="Failed to generate presigned URL for S3 object",
                error_code="S3_PRESIGNED_URL_ERROR",
                error_details={"key": key, "bucket": self._bucket},
                cause=e,
            ) from e

    def download_to(self, key: str, path: Path) -> None:
        validate_key(key)

        try:
            self._client.download_file(Bucket=self._bucket, Key=key, Filename=str(path))
        except (ClientError, BotoCoreError) as e:
            raise _storage_error(
                message="Failed to download S3 object to local path",
                error_code="S3_DOWNLOAD_ERROR",
                error_details={"key": key, "bucket": self._bucket, "path": str(path)},
                cause=e,
            ) from e
