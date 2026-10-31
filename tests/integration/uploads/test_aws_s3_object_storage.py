"""
Integration tests for AWSS3ObjectStorage.
"""

import os
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
from fastapi import HTTPException

from src.config.configs import settings
from src.uploads.storage.aws_s3_object_storage import AWSS3ObjectStorage

REGION = settings.uploads.S3_REGION
MOCK_BUCKET = "mock-bucket"
BAD_KEYS = ["", "/abs", "a//b", "../x", "a/./b", "a/../b", "a\\b", "a\x00b", "a/"]
BAD_PREFIXES = ["", "/", "..", "a/../b", "a//b"]


def make_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.uploads.S3_ENDPOINT_URL,
        aws_access_key_id=settings.uploads.S3_ACCESS_KEY_ID.get_secret_value(),
        aws_secret_access_key=settings.uploads.S3_SECRET_ACCESS_KEY.get_secret_value(),
        region_name=REGION,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=3,
            retries={"max_attempts": 1},
        ),
    )


def list_keys(client, bucket, prefix):
    keys = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(item["Key"] for item in page.get("Contents", []))
    return keys


def purge(client, bucket, prefix):
    keys = list_keys(client, bucket, prefix)
    for start in range(0, len(keys), 1000):
        batch = [{"Key": key} for key in keys[start : start + 1000]]
        client.delete_objects(Bucket=bucket, Delete={"Objects": batch, "Quiet": True})


def put_many(client, bucket, keys):
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(
            pool.map(
                lambda key: client.put_object(Bucket=bucket, Key=key, Body=b"x"), keys
            )
        )


def fetch(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.read()


def client_error(code, operation="Operation", http_status=None):
    response = {"Error": {"Code": code, "Message": code}}
    if http_status is not None:
        response["ResponseMetadata"] = {"HTTPStatusCode": http_status}
    return ClientError(response, operation)


def botocore_error():
    return EndpointConnectionError(endpoint_url="http://unreachable")


# A client-side fault is a 500. An unreachable or failing S3 is a 503.
ERROR_STATUSES = [
    (client_error("AccessDenied", http_status=403), 500),
    (client_error("NoSuchBucket", http_status=404), 500),
    (client_error("InternalError"), 500),
    (client_error("SlowDown", http_status=503), 503),
    (client_error("InternalError", http_status=500), 503),
    (botocore_error(), 503),
]


def assert_api_error(exc_info, status_code):
    assert exc_info.value.status_code == status_code


@pytest.fixture(scope="session")
def s3_client():
    return make_client()


@pytest.fixture(scope="session")
def bucket_name(s3_client):
    configured = os.getenv("S3_TEST_BUCKET")
    name = configured or f"askdocumind-test-{uuid.uuid4().hex[:12]}"
    try:
        if configured:
            s3_client.head_bucket(Bucket=name)
        else:
            kwargs = {"Bucket": name}
            if REGION != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": REGION}
            s3_client.create_bucket(**kwargs)
    except (ClientError, BotoCoreError) as e:
        pytest.skip(f"S3 endpoint is not available: {e}")
    yield name
    if not configured:
        purge(s3_client, name, "")
        s3_client.delete_bucket(Bucket=name)


@pytest.fixture
def storage(s3_client, bucket_name):
    return AWSS3ObjectStorage(s3_client, bucket_name)


@pytest.fixture
def prefix(s3_client, bucket_name):
    value = f"tests/{uuid.uuid4().hex}"
    yield value
    purge(s3_client, bucket_name, f"{value}/")


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def mock_storage(mock_client):
    return AWSS3ObjectStorage(mock_client, MOCK_BUCKET)


def test_save_and_load_roundtrip(storage, prefix):
    key = f"{prefix}/doc.txt"
    storage.save(key, b"hello world")
    assert storage.load(key) == b"hello world"


def test_save_overwrites_existing_key(storage, prefix):
    key = f"{prefix}/doc.txt"
    storage.save(key, b"first")
    storage.save(key, b"second")
    assert storage.load(key) == b"second"


def test_save_and_load_empty_bytes(storage, prefix):
    key = f"{prefix}/empty.bin"
    storage.save(key, b"")
    assert storage.load(key) == b""
    assert storage.exists(key)


def test_save_and_load_large_binary_payload(storage, prefix):
    key = f"{prefix}/large.bin"
    payload = os.urandom(6 * 1024 * 1024)
    storage.save(key, payload)
    assert storage.load(key) == payload


def test_load_missing_key_returns_none(storage, prefix):
    assert storage.load(f"{prefix}/missing.txt") is None


def test_exists_and_delete_lifecycle(storage, prefix):
    key = f"{prefix}/doc.txt"
    assert storage.exists(key) is False
    storage.save(key, b"data")
    assert storage.exists(key) is True
    storage.delete(key)
    assert storage.exists(key) is False
    assert storage.load(key) is None


def test_delete_missing_key_is_not_an_error(storage, prefix):
    storage.delete(f"{prefix}/never-existed.txt")


def test_keys_with_spaces_unicode_and_symbols(storage, prefix):
    names = [
        "my file.txt",
        "ünïcode-文件.pdf",
        "a+b&c=d.txt",
        "100%.txt",
        "deep/er/path.md",
    ]
    for name in names:
        key = f"{prefix}/{name}"
        storage.save(key, name.encode())
        assert storage.exists(key)
        assert storage.load(key) == name.encode()


def test_delete_prefix_removes_only_matching_objects(
    storage, s3_client, bucket_name, prefix
):
    inside = [f"{prefix}/p/a.txt", f"{prefix}/p/sub/b.txt"]
    outside = [f"{prefix}/pother/c.txt", f"{prefix}/p.txt"]
    for key in inside + outside:
        storage.save(key, b"x")

    assert storage.delete_prefix(f"{prefix}/p") == 2

    assert not any(storage.exists(key) for key in inside)
    assert all(storage.exists(key) for key in outside)


def test_delete_prefix_returns_zero_when_nothing_matches(storage, prefix):
    assert storage.delete_prefix(f"{prefix}/empty") == 0


def test_delete_prefix_accepts_trailing_slash(storage, prefix):
    storage.save(f"{prefix}/dir/a.txt", b"x")
    assert storage.delete_prefix(f"{prefix}/dir/") == 1
    assert not storage.exists(f"{prefix}/dir/a.txt")


def test_delete_prefix_handles_more_than_one_page(
    storage, s3_client, bucket_name, prefix
):
    keys = [f"{prefix}/bulk/{i:05d}.txt" for i in range(1005)]
    put_many(s3_client, bucket_name, keys)

    assert storage.delete_prefix(f"{prefix}/bulk") == 1005
    assert list_keys(s3_client, bucket_name, f"{prefix}/bulk/") == []


def test_presigned_url_downloads_object(storage, prefix):
    key = f"{prefix}/share.txt"
    storage.save(key, b"shared content")
    url = storage.presigned_url(key, 60)
    assert fetch(url) == b"shared content"


def test_presigned_url_expires(storage, prefix):
    key = f"{prefix}/short.txt"
    storage.save(key, b"data")
    url = storage.presigned_url(key, 1)
    time.sleep(2.5)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        fetch(url)
    assert exc_info.value.code == 403


def test_presigned_url_for_missing_key_returns_404_on_fetch(storage, prefix):
    url = storage.presigned_url(f"{prefix}/missing.txt", 60)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        fetch(url)
    assert exc_info.value.code == 404


def test_invalid_keys_are_rejected_before_any_s3_call(mock_client, mock_storage):
    calls = [
        lambda key: mock_storage.save(key, b"x"),
        mock_storage.load,
        mock_storage.delete,
        mock_storage.exists,
        lambda key: mock_storage.presigned_url(key, 60),
    ]
    for key in BAD_KEYS:
        for call in calls:
            with pytest.raises(HTTPException) as exc_info:
                call(key)
            assert_api_error(exc_info, 422)
    assert mock_client.mock_calls == []


def test_invalid_prefixes_are_rejected_and_data_is_kept(storage, prefix):
    keys = [f"{prefix}/a.txt", f"{prefix}/b.txt"]
    for key in keys:
        storage.save(key, b"x")

    for bad in BAD_PREFIXES:
        with pytest.raises(HTTPException) as exc_info:
            storage.delete_prefix(bad)
        assert_api_error(exc_info, 422)

    assert all(storage.exists(key) for key in keys)


def test_missing_bucket_raises_storage_errors(s3_client):
    broken = AWSS3ObjectStorage(s3_client, f"missing-{uuid.uuid4().hex}")

    with pytest.raises(HTTPException) as exc_info:
        broken.save("k", b"x")
    assert_api_error(exc_info, 500)

    with pytest.raises(HTTPException) as exc_info:
        broken.load("k")
    assert_api_error(exc_info, 500)


def test_check_available_passes_for_an_existing_bucket(storage):
    storage.check_available()


def test_check_available_raises_500_for_a_missing_bucket(s3_client):
    broken = AWSS3ObjectStorage(s3_client, f"missing-{uuid.uuid4().hex}")

    with pytest.raises(HTTPException) as exc_info:
        broken.check_available()
    assert_api_error(exc_info, 500)


def test_check_available_maps_errors_to_status_codes(mock_client, mock_storage):
    for cause, status_code in ERROR_STATUSES:
        mock_client.head_bucket.side_effect = cause
        with pytest.raises(HTTPException) as exc_info:
            mock_storage.check_available()
        assert_api_error(exc_info, status_code)


def test_save_delete_and_presign_wrap_client_errors(mock_client, mock_storage):
    operations = [
        ("put_object", lambda: mock_storage.save("k", b"x")),
        ("delete_object", lambda: mock_storage.delete("k")),
        ("generate_presigned_url", lambda: mock_storage.presigned_url("k", 60)),
    ]
    for method, call in operations:
        for cause, status_code in ERROR_STATUSES:
            getattr(mock_client, method).side_effect = cause
            with pytest.raises(HTTPException) as exc_info:
                call()
            assert_api_error(exc_info, status_code)


def test_load_wraps_unexpected_errors(mock_client, mock_storage):
    for cause, status_code in ERROR_STATUSES:
        mock_client.get_object.side_effect = cause
        with pytest.raises(HTTPException) as exc_info:
            mock_storage.load("k")
        assert_api_error(exc_info, status_code)


def test_load_returns_none_for_every_missing_code(mock_client, mock_storage):
    for code in ("NoSuchKey", "404", "NotFound"):
        mock_client.get_object.side_effect = client_error(code)
        assert mock_storage.load("k") is None


def test_exists_maps_missing_codes_and_wraps_other_errors(mock_client, mock_storage):
    for code in ("404", "NoSuchKey", "NotFound"):
        mock_client.head_object.side_effect = client_error(code)
        assert mock_storage.exists("k") is False

    for cause, status_code in [(client_error("403"), 500), *ERROR_STATUSES]:
        mock_client.head_object.side_effect = cause
        with pytest.raises(HTTPException) as exc_info:
            mock_storage.exists("k")
        assert_api_error(exc_info, status_code)


def test_delete_prefix_wraps_list_and_delete_errors(mock_client, mock_storage):
    paginate = mock_client.get_paginator.return_value.paginate

    for cause, status_code in ERROR_STATUSES:
        paginate.side_effect = cause
        with pytest.raises(HTTPException) as exc_info:
            mock_storage.delete_prefix("p")
        assert_api_error(exc_info, status_code)

    paginate.side_effect = None
    paginate.return_value = [{"Contents": [{"Key": "p/a"}]}]
    mock_client.delete_objects.side_effect = client_error("InternalError")
    with pytest.raises(HTTPException) as exc_info:
        mock_storage.delete_prefix("p")
    assert_api_error(exc_info, 500)


def test_delete_prefix_raises_when_s3_reports_partial_failures(
    mock_client, mock_storage
):
    mock_client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "p/a"}, {"Key": "p/b"}]}
    ]
    mock_client.delete_objects.return_value = {
        "Errors": [{"Key": "p/b", "Code": "AccessDenied"}]
    }
    with pytest.raises(HTTPException) as exc_info:
        mock_storage.delete_prefix("p")
    assert_api_error(exc_info, 500)
