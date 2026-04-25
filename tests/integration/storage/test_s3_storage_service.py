import os
from types import SimpleNamespace
from uuid import uuid4

import boto3
import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from src.database.storage.s3_storage_service import S3StorageService


def _require_s3_env_or_skip() -> tuple[str, str]:
    bucket = os.getenv("AWS_S3_BUCKET_NAME")
    region = os.getenv("AWS_REGION")

    if not bucket:
        pytest.skip("Set AWS_S3_BUCKET_NAME to run S3 integration tests.")

    if not region:
        region = boto3.session.Session().region_name

    if not region:
        pytest.skip("Set AWS_REGION or AWS_DEFAULT_REGION to run S3 tests.")

    return bucket, region


@pytest.fixture
def s3_integration_service(monkeypatch: pytest.MonkeyPatch):
    bucket, region = _require_s3_env_or_skip()

    client = boto3.client("s3", region_name=region)

    try:
        client.head_bucket(Bucket=bucket)
    except (NoCredentialsError, ClientError):
        pytest.skip(
            "AWS credentials/bucket access unavailable for S3 integration tests."
        )

    monkeypatch.setattr(
        "src.database.storage.s3_storage_service.settings.aws.S3_BUCKET_NAME", bucket
    )
    monkeypatch.setattr(
        "src.database.storage.s3_storage_service.settings.aws.REGION", region
    )

    service = S3StorageService()
    test_prefix = f"integration-tests/{uuid4()}/"

    yield SimpleNamespace(service=service, prefix=test_prefix)

    service.delete_all(test_prefix)


def test_constructor_uses_aws_env_values(monkeypatch: pytest.MonkeyPatch):
    bucket, region = _require_s3_env_or_skip()
    monkeypatch.setattr(
        "src.database.storage.s3_storage_service.settings.aws.S3_BUCKET_NAME", bucket
    )
    monkeypatch.setattr(
        "src.database.storage.s3_storage_service.settings.aws.REGION", region
    )

    service = S3StorageService()

    assert service.bucket == bucket


def test_save_load_and_exists_round_trip(s3_integration_service: SimpleNamespace):
    key = f"{s3_integration_service.prefix}round-trip.txt"
    payload = b"s3-bytes"

    s3_integration_service.service.save(key, payload)

    assert s3_integration_service.service.exists(key) is True
    assert s3_integration_service.service.load(key) == payload


def test_load_missing_key_returns_none(s3_integration_service: SimpleNamespace):
    key = f"{s3_integration_service.prefix}missing.txt"

    assert s3_integration_service.service.load(key) is None


def test_delete_existing_key_removes_it(s3_integration_service: SimpleNamespace):
    key = f"{s3_integration_service.prefix}delete-me.txt"
    s3_integration_service.service.save(key, b"x")

    deleted = s3_integration_service.service.delete(key)

    assert deleted == key
    assert s3_integration_service.service.exists(key) is False


def test_delete_missing_key_is_idempotent(s3_integration_service: SimpleNamespace):
    key = f"{s3_integration_service.prefix}already-gone.txt"

    deleted = s3_integration_service.service.delete(key)

    assert deleted == key


def test_exists_returns_false_for_missing_key(s3_integration_service: SimpleNamespace):
    key = f"{s3_integration_service.prefix}missing-exists.txt"

    assert s3_integration_service.service.exists(key) is False


def test_delete_all_prefix_deletes_only_prefix_keys(
    s3_integration_service: SimpleNamespace,
):
    key_a = f"{s3_integration_service.prefix}a.txt"
    key_b = f"{s3_integration_service.prefix}nested/b.txt"
    outside_key = f"integration-tests/outside-{uuid4()}.txt"

    s3_integration_service.service.save(key_a, b"a")
    s3_integration_service.service.save(key_b, b"b")
    s3_integration_service.service.save(outside_key, b"outside")

    deleted_count = s3_integration_service.service.delete_all(
        s3_integration_service.prefix
    )

    assert deleted_count == 2
    assert s3_integration_service.service.exists(key_a) is False
    assert s3_integration_service.service.exists(key_b) is False
    assert s3_integration_service.service.exists(outside_key) is True

    s3_integration_service.service.delete(outside_key)


def test_delete_all_missing_prefix_deletes_nothing(
    s3_integration_service: SimpleNamespace,
):
    missing_prefix = f"{s3_integration_service.prefix}missing/"

    assert s3_integration_service.service.delete_all(missing_prefix) == 0
