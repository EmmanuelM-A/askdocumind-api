"""
Global fixtures for pytest.
"""

import uuid
from typing import AsyncGenerator

import boto3
import pytest
import pytest_asyncio
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.configs import settings
from src.database.session import DatabaseSessionManager
from src.middleware.rate_limiter import limiter
from src.uploads.storage.aws_s3_object_storage import AWSS3ObjectStorage


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Stop rate limit counts leaking between tests."""
    limiter.reset()


@pytest_asyncio.fixture
async def manager():
    url = settings.database.DATABASE_URL.get_secret_value()

    if not url:
        pytest.skip("DATABASE_URL is not set")

    session_manager = DatabaseSessionManager(url)

    yield session_manager

    await session_manager.disconnect()


@pytest_asyncio.fixture
async def session(manager) -> AsyncGenerator[AsyncSession]:
    async with manager.engine.connect() as conn:
        outer = await conn.begin()
        async with AsyncSession(
            bind=conn,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        ) as db_session:
            yield db_session
        await outer.rollback()


@pytest.fixture(scope="session")
def _s3():
    """A throwaway bucket, emptied and removed at the end of the run."""
    client = boto3.client(
        "s3",
        endpoint_url=settings.uploads.S3_ENDPOINT_URL,
        aws_access_key_id=settings.uploads.S3_ACCESS_KEY_ID.get_secret_value(),
        aws_secret_access_key=settings.uploads.S3_SECRET_ACCESS_KEY.get_secret_value(),
        region_name=settings.uploads.S3_REGION,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=3,
            retries={"max_attempts": 1},
        ),
    )
    bucket = f"askdocumind-test-{uuid.uuid4().hex[:12]}"
    try:
        kwargs = {"Bucket": bucket}
        if settings.uploads.S3_REGION != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {
                "LocationConstraint": settings.uploads.S3_REGION
            }
        client.create_bucket(**kwargs)
    except (ClientError, BotoCoreError) as e:
        pytest.skip(f"S3 endpoint is not available: {e}")

    yield client, bucket

    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
    client.delete_bucket(Bucket=bucket)


@pytest.fixture
def object_storage(_s3):
    client, bucket = _s3
    return AWSS3ObjectStorage(client, bucket)
