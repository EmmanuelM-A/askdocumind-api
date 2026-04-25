from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from src.database.storage.s3_storage_service import S3StorageService


def _client_error(code: str, operation: str = "TestOperation") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


@pytest.fixture
def s3_setup(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    mock_client = Mock()

    monkeypatch.setattr(
        "src.database.storage.s3_storage_service.settings.aws.S3_BUCKET_NAME",
        "unit-test-bucket",
    )
    monkeypatch.setattr(
        "src.database.storage.s3_storage_service.settings.aws.REGION",
        "eu-west-2",
    )
    monkeypatch.setattr(
        "src.database.storage.s3_storage_service.boto3.client",
        Mock(return_value=mock_client),
    )

    service = S3StorageService()
    return SimpleNamespace(service=service, client=mock_client)


def test_constructor_raises_when_bucket_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "src.database.storage.s3_storage_service.settings.aws.S3_BUCKET_NAME",
        "",
    )
    monkeypatch.setattr(
        "src.database.storage.s3_storage_service.settings.aws.REGION",
        "eu-west-2",
    )

    with pytest.raises(ValueError, match="bucket name is not configured"):
        S3StorageService()


def test_constructor_raises_when_region_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "src.database.storage.s3_storage_service.settings.aws.S3_BUCKET_NAME",
        "unit-test-bucket",
    )
    monkeypatch.setattr(
        "src.database.storage.s3_storage_service.settings.aws.REGION",
        "",
    )

    with pytest.raises(ValueError, match="region is not configured"):
        S3StorageService()


def test_save_calls_put_object(s3_setup: SimpleNamespace):
    s3_setup.service.save("chat-1/file.txt", b"payload")

    s3_setup.client.put_object.assert_called_once_with(
        Bucket="unit-test-bucket",
        Key="chat-1/file.txt",
        Body=b"payload",
    )


def test_save_propagates_client_error(s3_setup: SimpleNamespace):
    s3_setup.client.put_object.side_effect = _client_error("AccessDenied", "PutObject")

    with pytest.raises(ClientError):
        s3_setup.service.save("chat-1/file.txt", b"payload")


def test_load_returns_bytes_when_key_exists(s3_setup: SimpleNamespace):
    body = Mock()
    body.read.return_value = b"abc"
    s3_setup.client.get_object.return_value = {"Body": body}

    result = s3_setup.service.load("chat-1/file.txt")

    assert result == b"abc"


def test_load_returns_none_when_key_missing(s3_setup: SimpleNamespace):
    s3_setup.client.get_object.side_effect = _client_error("NoSuchKey", "GetObject")

    result = s3_setup.service.load("chat-1/missing.txt")

    assert result is None


def test_load_returns_none_for_404_code(s3_setup: SimpleNamespace):
    s3_setup.client.get_object.side_effect = _client_error("404", "GetObject")

    assert s3_setup.service.load("chat-1/missing.txt") is None


def test_load_raises_for_non_missing_client_error(s3_setup: SimpleNamespace):
    s3_setup.client.get_object.side_effect = _client_error("AccessDenied", "GetObject")

    with pytest.raises(ClientError):
        s3_setup.service.load("chat-1/file.txt")


def test_delete_calls_delete_object_and_returns_key(s3_setup: SimpleNamespace):
    result = s3_setup.service.delete("chat-1/file.txt")

    assert result == "chat-1/file.txt"
    s3_setup.client.delete_object.assert_called_once_with(
        Bucket="unit-test-bucket",
        Key="chat-1/file.txt",
    )


def test_delete_propagates_client_error(s3_setup: SimpleNamespace):
    s3_setup.client.delete_object.side_effect = _client_error("AccessDenied", "DeleteObject")

    with pytest.raises(ClientError):
        s3_setup.service.delete("chat-1/file.txt")


def test_exists_returns_true_when_head_object_succeeds(s3_setup: SimpleNamespace):
    assert s3_setup.service.exists("chat-1/file.txt") is True


def test_exists_returns_false_when_object_not_found(s3_setup: SimpleNamespace):
    s3_setup.client.head_object.side_effect = _client_error("404", "HeadObject")

    assert s3_setup.service.exists("chat-1/missing.txt") is False


def test_exists_returns_false_for_not_found_code(s3_setup: SimpleNamespace):
    s3_setup.client.head_object.side_effect = _client_error("NotFound", "HeadObject")

    assert s3_setup.service.exists("chat-1/missing.txt") is False


def test_exists_raises_for_unexpected_client_error(s3_setup: SimpleNamespace):
    s3_setup.client.head_object.side_effect = _client_error("AccessDenied", "HeadObject")

    with pytest.raises(ClientError):
        s3_setup.service.exists("chat-1/file.txt")


def test_delete_all_deletes_all_objects_for_prefix(s3_setup: SimpleNamespace):
    paginator = Mock()
    paginator.paginate.return_value = [
        {"Contents": [{"Key": "chat-1/a.txt"}, {"Key": "chat-1/b.txt"}]},
        {"Contents": [{"Key": "chat-1/c.txt"}]},
    ]
    s3_setup.client.get_paginator.return_value = paginator

    deleted_count = s3_setup.service.delete_all("chat-1/")

    assert deleted_count == 3
    assert s3_setup.client.delete_objects.call_count == 2


def test_delete_all_without_key_uses_none_prefix(s3_setup: SimpleNamespace):
    paginator = Mock()
    paginator.paginate.return_value = [{"Contents": [{"Key": "a.txt"}]}]
    s3_setup.client.get_paginator.return_value = paginator

    deleted_count = s3_setup.service.delete_all()

    assert deleted_count == 1
    paginator.paginate.assert_called_once_with(Bucket="unit-test-bucket", Prefix=None)


def test_delete_all_with_empty_pages_returns_zero(s3_setup: SimpleNamespace):
    paginator = Mock()
    paginator.paginate.return_value = [{}, {"Contents": []}]
    s3_setup.client.get_paginator.return_value = paginator

    assert s3_setup.service.delete_all("chat-1/") == 0


