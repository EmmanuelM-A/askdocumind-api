"""
End-to-end tests for POST /v1/chatbot/{chat_session_id}/ask.
"""

import uuid

import pytest
import pytest_asyncio
from limits import parse

from src.config.configs import settings
from src.rag.schemas.retrieval import WebResult
from src.uploads.domain.document import DocumentStatus
from tests.e2e.chatbot.conftest import ANSWER

pytestmark = pytest.mark.asyncio

_QUESTION = "Where does the fleet gather?"
_RATE_LIMIT = parse(settings.server.RATE_LIMIT_CHATBOT).amount
_WEB_RESULT = WebResult(
    url="https://example.com/moon", title="Moon facts", content="The moon is far."
)


def _url(chat_session_id):
    return f"/v1/chatbot/{chat_session_id}/ask"


def _body(query=_QUESTION, **configs):
    return {"query": query, "configs": configs}


@pytest_asyncio.fixture
async def chat_id(user, make_chat):
    return await make_chat(user.user_id)


class TestAnswer:
    async def test_answers_from_the_chat_sessions_documents(
        self, client, user, chat_id, seed_document, answer_model
    ):
        await seed_document(chat_id, "report.pdf", [("Near the moon.", 0.9)])

        response = await client.post(_url(chat_id), json=_body(), headers=user.headers)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == {"answer": ANSWER, "sources": ["report.pdf"]}
        [prompt] = answer_model.prompts
        assert "Near the moon." in prompt
        assert _QUESTION in prompt

    async def test_sources_are_named_once_in_rank_order(
        self, client, user, chat_id, seed_document
    ):
        await seed_document(chat_id, "a.txt", [("best", 0.95), ("third", 0.7)])
        await seed_document(chat_id, "b.txt", [("second", 0.8)])

        response = await client.post(_url(chat_id), json=_body(), headers=user.headers)

        assert response.json()["data"]["sources"] == ["a.txt", "b.txt"]

    async def test_top_k_limits_the_chunks_given_to_the_model(
        self, client, user, chat_id, seed_document, answer_model
    ):
        await seed_document(
            chat_id, "a.txt", [("best", 0.9), ("second", 0.8), ("third", 0.7)]
        )

        await client.post(_url(chat_id), json=_body(topK=1), headers=user.headers)

        [prompt] = answer_model.prompts
        assert "best" in prompt
        assert "second" not in prompt
        assert "third" not in prompt

    async def test_no_relevant_chunks_answers_without_the_model(
        self, client, user, chat_id, seed_document, answer_model
    ):
        await seed_document(chat_id, "unrelated.txt", [("Cooking pasta.", 0.1)])

        response = await client.post(_url(chat_id), json=_body(), headers=user.headers)

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["sources"] == []
        assert data["answer"]
        assert answer_model.prompts == []

    async def test_ignores_documents_in_other_chat_sessions(
        self, client, user, chat_id, make_chat, seed_document, answer_model
    ):
        other_chat_id = await make_chat(user.user_id)
        await seed_document(other_chat_id, "elsewhere.txt", [("Near the moon.", 0.9)])

        response = await client.post(_url(chat_id), json=_body(), headers=user.headers)

        assert response.json()["data"]["sources"] == []
        assert answer_model.prompts == []

    async def test_ignores_documents_that_are_not_processed(
        self, client, user, chat_id, seed_document, answer_model
    ):
        await seed_document(
            chat_id,
            "pending.txt",
            [("Near the moon.", 0.9)],
            status=DocumentStatus.PROCESSING,
        )

        response = await client.post(_url(chat_id), json=_body(), headers=user.headers)

        assert response.json()["data"]["sources"] == []
        assert answer_model.prompts == []

    async def test_model_failure_is_a_server_error(
        self, client, user, chat_id, seed_document, answer_model
    ):
        await seed_document(chat_id, "report.pdf", [("Near the moon.", 0.9)])
        answer_model.error = RuntimeError("OpenAI is down")

        response = await client.post(_url(chat_id), json=_body(), headers=user.headers)

        assert response.status_code == 500


class TestWebSearch:
    async def test_answers_from_the_web_when_documents_fall_short(
        self, client, user, chat_id, web_searcher, answer_model
    ):
        web_searcher.results = [_WEB_RESULT]

        response = await client.post(
            _url(chat_id), json=_body(webSearchEnabled=True), headers=user.headers
        )

        assert response.json()["data"]["sources"] == ["Moon facts"]
        assert web_searcher.calls == [_QUESTION]
        assert "The moon is far." in answer_model.prompts[0]

    async def test_web_sources_come_after_document_sources(
        self, client, user, chat_id, seed_document, web_searcher
    ):
        await seed_document(chat_id, "report.pdf", [("Near the moon.", 0.9)])
        web_searcher.results = [_WEB_RESULT]

        response = await client.post(
            _url(chat_id), json=_body(webSearchEnabled=True), headers=user.headers
        )

        assert response.json()["data"]["sources"] == ["report.pdf", "Moon facts"]

    async def test_web_is_not_searched_unless_enabled(
        self, client, user, chat_id, web_searcher
    ):
        web_searcher.results = [_WEB_RESULT]

        response = await client.post(_url(chat_id), json=_body(), headers=user.headers)

        assert web_searcher.calls == []
        assert response.json()["data"]["sources"] == []

    async def test_web_is_not_searched_when_documents_are_enough(
        self, client, user, chat_id, seed_document, web_searcher
    ):
        needed = settings.rag.MIN_CHUNKS_NEEDED_FOR_WEB_SEARCH
        await seed_document(
            chat_id, "report.pdf", [(f"chunk {i}", 0.9) for i in range(needed)]
        )

        await client.post(
            _url(chat_id), json=_body(webSearchEnabled=True), headers=user.headers
        )

        assert web_searcher.calls == []


class TestValidation:
    @pytest.mark.parametrize(
        "body",
        [
            {"configs": {}},
            _body(query=""),
            _body(query="x" * 2001),
            _body(topK=0),
            _body(threshold=1.5),
        ],
        ids=["no-query", "empty-query", "long-query", "zero-top-k", "high-threshold"],
    )
    async def test_invalid_body_is_rejected_before_any_paid_call(
        self, client, user, chat_id, expander, body
    ):
        response = await client.post(_url(chat_id), json=body, headers=user.headers)

        assert response.status_code == 422
        assert expander.calls == []


class TestAccess:
    async def test_another_users_chat_session_is_forbidden(
        self, client, chat_id, seed_document, make_user, expander
    ):
        await seed_document(chat_id, "private.pdf", [("Secret plans.", 0.9)])
        intruder = await make_user()

        response = await client.post(
            _url(chat_id), json=_body(), headers=intruder.headers
        )

        assert response.status_code == 403
        assert expander.calls == []

    async def test_unknown_chat_session_is_not_found(self, client, user, expander):
        response = await client.post(
            _url(uuid.uuid4()), json=_body(), headers=user.headers
        )

        assert response.status_code == 404
        assert expander.calls == []

    async def test_missing_cookie_is_unauthorized(self, client, chat_id, expander):
        response = await client.post(_url(chat_id), json=_body())

        assert response.status_code == 401
        assert expander.calls == []


class TestRateLimit:
    async def test_requests_over_the_limit_are_rejected(
        self, client, user, chat_id, expander
    ):
        for _ in range(_RATE_LIMIT):
            response = await client.post(
                _url(chat_id), json=_body(), headers=user.headers
            )
            assert response.status_code == 200

        response = await client.post(_url(chat_id), json=_body(), headers=user.headers)

        assert response.status_code == 429
        assert len(expander.calls) == _RATE_LIMIT
