from typing import Optional

from botocore.exceptions import ClientError
import boto3

from src.config.configs import settings
from src.database.storage.storage_service import StorageService


class S3StorageService(StorageService):
    def __init__(self) -> None:
        if not settings.aws.S3_BUCKET_NAME:
            raise ValueError("AWS S3 bucket name is not configured.")

        if not settings.aws.REGION:
            raise ValueError("AWS region is not configured.")

        self.bucket = settings.aws.S3_BUCKET_NAME
        self.s3_client = boto3.client("s3", region_name=settings.aws.REGION)

    def save(self, key: str, data: bytes) -> None:
        self.s3_client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def load(self, key: str) -> Optional[bytes]:
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket,
                Key=key,
            )
            return response["Body"].read()
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"NoSuchKey", "404"}:
                return None
            raise

    def delete(self, key: str) -> Optional[str]:
        self.s3_client.delete_object(Bucket=self.bucket, Key=key)
        return key

    def exists(self, key: str) -> bool:
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def delete_all(self, key: str | None = None) -> int:
        deleted = 0

        paginator = self.s3_client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self.bucket, Prefix=key):
            contents = page.get("Contents", [])
            if not contents:
                continue

            objs = [{"Key": item["Key"]} for item in contents]
            self.s3_client.delete_objects(Bucket=self.bucket, Delete={"Objects": objs})
            deleted += len(objs)

        return deleted
