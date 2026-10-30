"""
Shared fixtures for the chatbot endpoint e2e tests.

Requests go through the real app: its middleware, cookie authentication, rate
limits, the ownership check, the pgvector similarity search, the passthrough
reranker and the real answer prompt. Only the paid or networked services are
faked: the query expander, the embedder, the web searcher and the answer
model. Each fake records its calls.
"""

import hashlib
import uuid
from math import sqrt

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import src.database.models  # noqa: F401  registers every model for the mappers
from src.app import create_app
from src.chatbot.services import chatbot_service
from src.config.configs import settings
from src.rag.dependencies import get_embedder, get_query_expander, get_web_searcher
from src.rag.models.chunk_embedding import ChunkEmbedding
from src.rag.schemas.retrieval import WebResult
from src.rag.services.embed.embedder import Embedder
from src.rag.services.expand.query_expander import QueryExpander
from src.rag.services.fallback.web_searcher import WebSearcher
from src.rag.services.rerank.passthrough_reranker import PassthroughReranker
from src.uploads.domain.document import DocumentStatus
from src.uploads.models.document import Document

ANSWER = "The fleet gathers near the moon."


def vector(similarity):
    """A unit vector whose cosine similarity to the query vector is `similarity`."""
    values = [0.0] * settings.rag.EMBEDDING_DIMENSIONS
    values[0] = similarity
    values[1] = sqrt(1 - similarity**2)
    return values


class FakeQueryExpander(QueryExpander):
    def __init__(self):
        self.calls = []

    async def expand(self, query):
        self.calls.append(query)
        return query


class FakeEmbedder(Embedder):
    async def embed_chunks(self, chunks):
        raise NotImplementedError

    async def embed_query(self, query):
        return vector(1.0)


class FakeWebSearcher(WebSearcher):
    def __init__(self):
        self.results: list[WebResult] = []
        self.calls = []

    async def search_web(self, query):
        self.calls.append(query)
        return list(self.results)

    def search_web_stream(self, query):
        raise NotImplementedError


class FakeAnswerModel:
    """Stands in for ChatOpenAI, and records the prompt's user message."""

    def __init__(self):
        self.prompts = []
        self.error = None
        self.runnable = RunnableLambda(self._invoke)

    def _invoke(self, prompt):
        self.prompts.append(prompt.to_messages()[-1].content)
        if self.error is not None:
            raise self.error
        return AIMessage(content=ANSWER)


@pytest.fixture
def expander():
    return FakeQueryExpander()


@pytest.fixture
def web_searcher():
    return FakeWebSearcher()


@pytest.fixture
def answer_model():
    return FakeAnswerModel()


@pytest.fixture
def app(manager, expander, web_searcher, answer_model, monkeypatch):
    monkeypatch.setattr(
        chatbot_service, "ChatOpenAI", lambda **_: answer_model.runnable
    )
    # The lifespan is not run by the test transport, so set its state here.
    app = create_app()
    app.state.session_manager = manager
    app.state.reranker = PassthroughReranker()
    app.dependency_overrides[get_query_expander] = lambda: expander
    app.dependency_overrides[get_embedder] = FakeEmbedder
    app.dependency_overrides[get_web_searcher] = lambda: web_searcher
    return app


@pytest.fixture
def seed_document(manager):
    """Commit a document with one chunk per (text, similarity) pair."""

    async def _seed(chat_session_id, filename, chunks, status=DocumentStatus.COMPLETED):
        document_id = uuid.uuid4()
        async with manager.get_session() as session:
            session.add(
                Document(
                    id=document_id,
                    chat_session_id=chat_session_id,
                    original_filename=filename,
                    object_key=f"{chat_session_id}/{document_id}",
                    content_type="text/plain",
                    size_bytes=1,
                    checksum=hashlib.sha256(filename.encode()).hexdigest(),
                    status=status,
                )
            )
            await session.flush()
            session.add_all(
                ChunkEmbedding(
                    document_id=document_id,
                    chat_session_id=chat_session_id,
                    chunk_index=index,
                    chunk_text=text,
                    embedding=vector(similarity),
                )
                for index, (text, similarity) in enumerate(chunks)
            )
        return document_id

    return _seed
