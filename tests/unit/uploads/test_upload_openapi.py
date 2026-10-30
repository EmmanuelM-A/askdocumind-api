"""
Checks the upload route's OpenAPI schema, which /docs and generated clients
use to build the request.
"""

from fastapi.testclient import TestClient

from src.app import create_app


def test_upload_is_documented_as_multipart():
    # Not entered as a context manager, so the lifespan doesn't run
    spec = TestClient(create_app()).get("/openapi.json").json()

    body = spec["paths"]["/v1/uploads/{chat_session_id}"]["post"]["requestBody"]

    # application/x-www-form-urlencoded can't carry a file, so /docs would
    # send the form without it and get "file: Field required"
    assert list(body["content"]) == ["multipart/form-data"]
