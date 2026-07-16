"""
End-to-end tests for POST /api/auth/anonymous (create/reuse anonymous user
session). No dependency is mocked anywhere in this file — every test hits
the real FastAPI app, the real database, and the real TokenManager.
"""

import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from src.api.utils.session_manager import TokenManager
from src.config.configs import settings

ENDPOINT = "/api/auth/anonymous"
COOKIE_NAME = settings.auth.COOKIE_NAME


def _parse_set_cookie(header_value: str) -> dict:
    """Parses a raw Set-Cookie header string into a lowercase-keyed dict.
    Flag-only attributes (HttpOnly, Secure) map to True."""

    parts = [p.strip() for p in header_value.split(";")]
    parsed: dict = {}
    for i, part in enumerate(parts):
        if i == 0:
            continue
        if "=" in part:
            key, _, value = part.partition("=")
            parsed[key.strip().lower()] = value.strip()
        else:
            parsed[part.strip().lower()] = True
    return parsed


# ============================ New-session happy path ============================


async def test_no_cookie_creates_new_user_returns_201(app_client, created_user_ids):
    response = app_client.post(ENDPOINT)

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Anonymous user session created successfully."

    user_id = UUID(body["data"]["user_id"])
    created_user_ids.append(user_id)


async def test_no_cookie_persists_user_row_in_db(app_client, user_repo, created_user_ids):
    response = app_client.post(ENDPOINT)
    user_id = UUID(response.json()["data"]["user_id"])
    created_user_ids.append(user_id)

    stored_user = await user_repo.get_by_id(user_id)

    assert stored_user is not None
    assert stored_user.created_at is not None
    assert stored_user.last_seen_at is not None


async def test_no_cookie_sets_set_cookie_header(app_client, created_user_ids):
    response = app_client.post(ENDPOINT)
    created_user_ids.append(UUID(response.json()["data"]["user_id"]))

    assert response.headers.get("set-cookie") is not None
    assert COOKIE_NAME in response.cookies


async def test_set_cookie_attributes_match_settings(app_client, created_user_ids):
    response = app_client.post(ENDPOINT)
    created_user_ids.append(UUID(response.json()["data"]["user_id"]))

    raw_cookie = response.headers.get("set-cookie")
    assert raw_cookie is not None

    attrs = _parse_set_cookie(raw_cookie)
    same_site = settings.auth.COOKIE_SAMESITE.lower()

    assert attrs.get("httponly") is True
    assert attrs.get("path") == "/"
    assert attrs.get("samesite", "").lower() == same_site
    assert attrs.get("secure", False) is (True if same_site == "none" else attrs.get("secure", False))

    if settings.auth.COOKIE_DOMAIN:
        assert attrs.get("domain") == settings.auth.COOKIE_DOMAIN
    else:
        assert "domain" not in attrs

    expected_max_age = max(int(settings.anon.TTL_HOURS * 60 * 60), 1)
    assert "max-age" in attrs
    assert abs(int(attrs["max-age"]) - expected_max_age) <= 2


async def test_returned_cookie_decodes_to_returned_user_id(app_client, token_manager, created_user_ids):
    response = app_client.post(ENDPOINT)
    body = response.json()
    user_id = UUID(body["data"]["user_id"])
    created_user_ids.append(user_id)

    cookie_token = response.cookies.get(COOKIE_NAME)
    assert cookie_token is not None

    payload = token_manager.decode_token(cookie_token)
    assert payload.user_id == user_id


async def test_response_does_not_leak_internal_fields(app_client, created_user_ids):
    response = app_client.post(ENDPOINT)
    body = response.json()
    created_user_ids.append(UUID(body["data"]["user_id"]))

    assert set(body.keys()) == {"success", "timestamp", "message", "data"}
    assert set(body["data"].keys()) == {"user_id"}


async def test_timestamp_field_is_recent(app_client, created_user_ids):
    response = app_client.post(ENDPOINT)
    body = response.json()
    created_user_ids.append(UUID(body["data"]["user_id"]))

    raw_timestamp = body["timestamp"]
    # Response timestamps are formatted as DD-MM-YYYY HH:MM:SS in Europe/London
    # time (see src/utils/datetime_utils.py::format_datetime) — not ISO-8601.
    parsed_naive = datetime.strptime(raw_timestamp, "%d-%m-%Y %H:%M:%S")
    parsed = parsed_naive.replace(tzinfo=ZoneInfo("Europe/London"))

    delta = abs((datetime.now(timezone.utc) - parsed).total_seconds())
    assert delta < 10


# =============================== Session reuse ===============================


async def test_valid_cookie_for_existing_user_reuses_session(app_client, token_manager, seed_user):
    user_id = await seed_user()
    cookie_token = token_manager.create_token(user_id)

    response = app_client.post(ENDPOINT, cookies={COOKIE_NAME: cookie_token})

    assert response.status_code == 201
    assert response.json()["data"]["user_id"] == str(user_id)


async def test_valid_cookie_updates_last_seen_at(app_client, token_manager, user_repo, seed_user):
    older_last_seen = datetime.now(timezone.utc) - timedelta(hours=1)
    user_id = await seed_user(last_seen_at=older_last_seen)
    cookie_token = token_manager.create_token(user_id)

    app_client.post(ENDPOINT, cookies={COOKIE_NAME: cookie_token})

    refreshed = await user_repo.get_by_id(user_id)

    assert refreshed is not None
    assert refreshed.last_seen_at > older_last_seen.replace(tzinfo=timezone.utc)


async def test_valid_cookie_reuse_does_not_create_extra_row(app_client, token_manager, user_repo, seed_user):
    user_id = await seed_user()
    cookie_token = token_manager.create_token(user_id)

    before = await user_repo.get_by_id(user_id)
    assert before is not None

    response = app_client.post(ENDPOINT, cookies={COOKIE_NAME: cookie_token})
    assert response.json()["data"]["user_id"] == str(user_id)

    after = await user_repo.get_by_id(user_id)

    assert after is not None
    assert after.id == before.id
    assert after.created_at == before.created_at


# ==================== Bad-cookie-falls-back-to-new-user family ====================


async def test_garbage_cookie_falls_back_to_new_user(app_client, created_user_ids):
    response = app_client.post(ENDPOINT, cookies={COOKIE_NAME: "not-a-real-token"})

    assert response.status_code == 201
    user_id = UUID(response.json()["data"]["user_id"])
    created_user_ids.append(user_id)


async def test_tampered_signature_cookie_falls_back_to_new_user(app_client, token_manager, user_repo, seed_user, created_user_ids):
    user_id = await seed_user()
    valid_token = token_manager.create_token(user_id)

    payload_part, signature_part = valid_token.split(".", 1)
    tampered_signature = signature_part[::-1] if signature_part[::-1] != signature_part else signature_part + "x"
    tampered_token = f"{payload_part}.{tampered_signature}"

    response = app_client.post(ENDPOINT, cookies={COOKIE_NAME: tampered_token})

    assert response.status_code == 201
    new_user_id = UUID(response.json()["data"]["user_id"])
    assert new_user_id != user_id
    created_user_ids.append(new_user_id)

    original = await user_repo.get_by_id(user_id)
    assert original is not None


async def test_expired_cookie_falls_back_to_new_user(app_client, user_repo, seed_user, created_user_ids):
    user_id = await seed_user()

    short_lived_manager = TokenManager(
        secret=settings.auth.USER_SESSION_SECRET.get_secret_value(),
        ttl_hours=1 / 3600,  # 1 second
    )
    expiring_token = short_lived_manager.create_token(user_id)
    time.sleep(1.1)

    response = app_client.post(ENDPOINT, cookies={COOKIE_NAME: expiring_token})

    assert response.status_code == 201
    new_user_id = UUID(response.json()["data"]["user_id"])
    assert new_user_id != user_id
    created_user_ids.append(new_user_id)

    original = await user_repo.get_by_id(user_id)
    assert original is not None


async def test_valid_signature_nonexistent_user_falls_back_to_new_user(app_client, token_manager, user_repo, created_user_ids):
    random_user_id = uuid4()
    cookie_token = token_manager.create_token(random_user_id)

    response = app_client.post(ENDPOINT, cookies={COOKIE_NAME: cookie_token})

    assert response.status_code == 201
    new_user_id = UUID(response.json()["data"]["user_id"])
    assert new_user_id != random_user_id
    created_user_ids.append(new_user_id)

    persisted = await user_repo.get_by_id(new_user_id)
    assert persisted is not None


async def test_malformed_token_missing_dot_separator_falls_back(app_client, created_user_ids):
    response = app_client.post(ENDPOINT, cookies={COOKIE_NAME: "nodotsatall12345"})

    assert response.status_code == 201
    created_user_ids.append(UUID(response.json()["data"]["user_id"]))


async def test_empty_string_cookie_falls_back_to_new_user(app_client, created_user_ids):
    # Note: depending on how the HTTP client serializes an empty cookie value,
    # this may end up behaviorally identical to sending no cookie at all —
    # both paths go through the same "cookie_value is falsy" branch.
    response = app_client.post(ENDPOINT, cookies={COOKIE_NAME: ""})

    assert response.status_code == 201
    created_user_ids.append(UUID(response.json()["data"]["user_id"]))


# ========================= Isolation / HTTP-layer edges =========================


async def test_two_sequential_no_cookie_calls_create_two_distinct_users(app_client, created_user_ids):
    response_1 = app_client.post(ENDPOINT)
    response_2 = app_client.post(ENDPOINT)

    user_id_1 = UUID(response_1.json()["data"]["user_id"])
    user_id_2 = UUID(response_2.json()["data"]["user_id"])

    assert user_id_1 != user_id_2
    created_user_ids.extend([user_id_1, user_id_2])


async def test_get_method_not_allowed(app_client):
    response = app_client.get(ENDPOINT)

    assert response.status_code == 405
    assert response.headers.get("set-cookie") is None


async def test_trailing_slash_returns_404(app_client):
    response = app_client.post(f"{ENDPOINT}/", follow_redirects=False)

    assert response.status_code == 404


async def test_wrong_prefix_path_returns_404(app_client):
    response = app_client.post("/auth/anonymous")

    assert response.status_code == 404
