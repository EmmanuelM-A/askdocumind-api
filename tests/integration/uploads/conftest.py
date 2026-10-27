"""
Shared fixtures for the upload integration tests: a throwaway S3 bucket and
chat sessions committed through the real session manager.
"""

import uuid

import boto3
import pytest
import pytest_asyncio
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import delete

import src.database.models  # noqa: F401  registers every model for the mappers
from src.auth.models.user import User
from src.chat_session.models.chat_session import ChatSession
from src.config.configs import settings
from src.uploads.storage.aws_s3_object_storage import AWSS3ObjectStorage


@pytest.fixture(scope="session")
def _s3():
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


@pytest_asyncio.fixture
async def new_chat_session(manager):
    """Create committed chat sessions; their users are deleted afterwards."""
    users = []

    async def _create():
        async with manager.get_session() as session:
            user = User()
            session.add(user)
            await session.flush()
            chat_session = ChatSession(user_id=user.id, title="test")
            session.add(chat_session)
            await session.flush()
        users.append(user.id)
        return chat_session.id

    yield _create

    async with manager.get_session() as session:
        await session.execute(delete(User).where(User.id.in_(users)))
