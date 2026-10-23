"""
Integration tests for ChunkEmbeddingRepositoryImpl.
"""

import datetime as dt
import importlib
from math import sqrt

import pkgutil
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as SATimeoutError


from src.config.configs import settings
from src.database.orm_base import Base
from src.exceptions.base import ApiException
from src.rag.models.chunk_embedding import ChunkEmbedding
from src.rag.repository.chunk_embedding_repository_impl import (
    ChunkEmbeddingRepositoryImpl,
)
from src.uploads.domain.document import DocumentStatus


def _import_all_models():
    import src

    for info in pkgutil.walk_packages(src.__path__, "src.", onerror=lambda name: None):
        if ".models" in info.name:
            importlib.import_module(info.name)


_import_all_models()

pytestmark = pytest.mark.asyncio

DIMENSIONS = settings.rag.EMBEDDING_DIMENSIONS
CONFLICT = 409
INTERNAL_ERROR = 500
UNAVAILABLE = 503


def _dummy(column):
    column_type = column.type
    if isinstance(column_type, sa.Enum) and column_type.enums:
        return column_type.enums[0]
    python_type = column_type.python_type
    values = {
        str: f"test-{uuid.uuid4().hex[:8]}",
        int: 1,
        float: 1.0,
        bool: False,
        bytes: b"x",
        dict: {},
        list: [],
        Decimal: Decimal(1),
        uuid.UUID: uuid.uuid4(),
        dt.datetime: dt.datetime.now(dt.timezone.utc),
        dt.date: dt.date.today(),
    }
    return values[python_type] if python_type in values else python_type()


async def _insert(session, table, **overrides):
    values = dict(overrides)
    for column in table.columns:
        if column.name in values:
            continue
        if column.foreign_keys:
            if column.nullable:
                continue
            foreign_key = next(iter(column.foreign_keys))
            parent = await _insert(session, foreign_key.column.table)
            values[column.name] = parent[foreign_key.column.name]
        elif column.primary_key:
            if isinstance(column.type, sa.Integer):
                continue
            values[column.name] = _dummy(column)
        elif (
            column.nullable
            or column.default is not None
            or column.server_default is not None
        ):
            continue
        else:
            values[column.name] = _dummy(column)
    result = await session.execute(table.insert().values(**values).returning(table))
    return dict(result.mappings().one())


async def _parents(session, chat_session_id=None):
    tables = Base.metadata.tables
    if chat_session_id is None:
        chat_session_id = (await _insert(session, tables["chat_sessions"]))["id"]
    document_overrides = {}
    if "chat_session_id" in tables["documents"].c:
        document_overrides["chat_session_id"] = chat_session_id
    document_id = (await _insert(session, tables["documents"], **document_overrides))[
        "id"
    ]
    return chat_session_id, document_id


def _vector(index=0):
    return [0.1 + 0.01 * index] * DIMENSIONS


QUERY = [1.0] + [0.0] * (DIMENSIONS - 1)


def _similar_to_query(similarity):
    """A unit vector whose cosine similarity to QUERY is `similarity`."""
    return [similarity, sqrt(1 - similarity**2)] + [0.0] * (DIMENSIONS - 2)


def _chunk(chat_session_id, document_id, index=0, embedding=None):
    return ChunkEmbedding(
        id=uuid.uuid4(),
        document_id=document_id,
        chat_session_id=chat_session_id,
        chunk_index=index,
        chunk_text=f"chunk {index}",
        embedding=embedding if embedding is not None else _vector(index),
    )


async def _seed(repo, chat_session_id, document_id, count):
    chunks = [_chunk(chat_session_id, document_id, i) for i in range(count)]
    await repo.create_many(chunks)
    return chunks


async def _seed_similar(repo, chat_session_id, document_id, similarities):
    chunks = [
        _chunk(chat_session_id, document_id, i, _similar_to_query(similarity))
        for i, similarity in enumerate(similarities)
    ]
    await repo.create_many(chunks)
    return chunks


async def _set_status(session, document_id, status):
    table = Base.metadata.tables["documents"]
    await session.execute(
        table.update().where(table.c.id == document_id).values(status=status)
    )


async def _completed_parents(session, chat_session_id=None):
    chat_session_id, document_id = await _parents(session, chat_session_id)
    await _set_status(session, document_id, DocumentStatus.COMPLETED)
    return chat_session_id, document_id


async def _ids(session, **filters):
    statement = select(ChunkEmbedding.id)
    for name, value in filters.items():
        statement = statement.where(getattr(ChunkEmbedding, name) == value)
    return set((await session.execute(statement)).scalars().all())


async def _row_exists(session, table_name, row_id):
    table = Base.metadata.tables[table_name]
    result = await session.execute(select(table.c.id).where(table.c.id == row_id))
    return result.scalar_one_or_none() is not None


@pytest.fixture
def repo(session):
    return ChunkEmbeddingRepositoryImpl(session)


@pytest_asyncio.fixture
async def parents(session):
    return await _parents(session)


@pytest_asyncio.fixture
async def completed_parents(session):
    return await _completed_parents(session)


class TestCreateMany:
    async def test_persists_all_chunks_and_returns_count(self, repo, session, parents):
        chat_session_id, document_id = parents
        chunks = [_chunk(chat_session_id, document_id, i) for i in range(3)]

        assert await repo.create_many(chunks) == 3
        assert await _ids(session, document_id=document_id) == {c.id for c in chunks}

    async def test_empty_list_returns_zero(self, repo, session, parents):
        chat_session_id, _ = parents

        assert await repo.create_many([]) == 0
        assert await _ids(session, chat_session_id=chat_session_id) == set()

    async def test_single_chunk(self, repo, session, parents):
        chat_session_id, document_id = parents
        chunk = _chunk(chat_session_id, document_id)

        assert await repo.create_many([chunk]) == 1
        assert await _ids(session, id=chunk.id) == {chunk.id}

    async def test_large_batch(self, repo, session, parents):
        chat_session_id, document_id = parents

        assert len(await _seed(repo, chat_session_id, document_id, 100)) == 100
        assert len(await _ids(session, document_id=document_id)) == 100

    async def test_stored_fields_and_embedding_round_trip(self, repo, session, parents):
        chat_session_id, document_id = parents
        chunk = _chunk(chat_session_id, document_id, index=4)
        await repo.create_many([chunk])

        result = await session.execute(
            select(
                ChunkEmbedding.chunk_index,
                ChunkEmbedding.chunk_text,
                ChunkEmbedding.created_at,
                ChunkEmbedding.embedding,
            ).where(ChunkEmbedding.id == chunk.id)
        )
        chunk_index, chunk_text, created_at, embedding = result.one()

        assert chunk_index == 4
        assert chunk_text == "chunk 4"
        assert created_at is not None
        assert [float(v) for v in embedding] == pytest.approx(_vector(4), rel=1e-4)

    async def test_same_chunk_index_in_different_documents_is_allowed(
        self, repo, session, parents
    ):
        chat_session_id, first_document = parents
        _, second_document = await _parents(session, chat_session_id)

        await repo.create_many([_chunk(chat_session_id, first_document, 0)])
        await repo.create_many([_chunk(chat_session_id, second_document, 0)])

        assert len(await _ids(session, chat_session_id=chat_session_id)) == 2

    async def test_duplicate_chunk_index_for_document_conflicts(self, repo, parents):
        chat_session_id, document_id = parents
        await repo.create_many([_chunk(chat_session_id, document_id, 0)])

        with pytest.raises(ApiException) as exc:
            await repo.create_many([_chunk(chat_session_id, document_id, 0)])
        assert exc.value.status_code == CONFLICT

    async def test_duplicate_chunk_index_within_batch_conflicts(self, repo, parents):
        chat_session_id, document_id = parents
        batch = [
            _chunk(chat_session_id, document_id, 0),
            _chunk(chat_session_id, document_id, 0),
        ]

        with pytest.raises(ApiException) as exc:
            await repo.create_many(batch)
        assert exc.value.status_code == CONFLICT

    async def test_unknown_document_conflicts(self, repo, parents):
        chat_session_id, _ = parents

        with pytest.raises(ApiException) as exc:
            await repo.create_many([_chunk(chat_session_id, uuid.uuid4())])
        assert exc.value.status_code == CONFLICT

    async def test_unknown_chat_session_conflicts(self, repo, parents):
        _, document_id = parents

        with pytest.raises(ApiException) as exc:
            await repo.create_many([_chunk(uuid.uuid4(), document_id)])
        assert exc.value.status_code == CONFLICT

    async def test_wrong_embedding_dimension_raises(self, repo, parents):
        chat_session_id, document_id = parents
        chunk = _chunk(chat_session_id, document_id, embedding=[0.1] * (DIMENSIONS + 1))

        with pytest.raises(ApiException) as exc:
            await repo.create_many([chunk])
        assert exc.value.status_code == INTERNAL_ERROR


class TestDeleteByChatSession:
    async def test_deletes_all_chunks_and_returns_count(self, repo, session, parents):
        chat_session_id, document_id = parents
        await _seed(repo, chat_session_id, document_id, 4)

        assert await repo.delete_by_chat_session(chat_session_id) == 4
        assert await _ids(session, chat_session_id=chat_session_id) == set()

    async def test_deletes_chunks_across_documents(self, repo, session, parents):
        chat_session_id, first_document = parents
        _, second_document = await _parents(session, chat_session_id)
        await _seed(repo, chat_session_id, first_document, 2)
        await _seed(repo, chat_session_id, second_document, 3)

        assert await repo.delete_by_chat_session(chat_session_id) == 5

    async def test_leaves_other_chat_sessions_untouched(self, repo, session, parents):
        chat_session_id, document_id = parents
        other_chat_session, other_document = await _parents(session)
        await _seed(repo, chat_session_id, document_id, 2)
        survivors = await _seed(repo, other_chat_session, other_document, 3)

        await repo.delete_by_chat_session(chat_session_id)

        assert await _ids(session, chat_session_id=other_chat_session) == {
            c.id for c in survivors
        }

    async def test_parent_rows_are_kept(self, repo, session, parents):
        chat_session_id, document_id = parents
        await _seed(repo, chat_session_id, document_id, 2)

        await repo.delete_by_chat_session(chat_session_id)

        assert await _row_exists(session, "chat_sessions", chat_session_id)
        assert await _row_exists(session, "documents", document_id)

    async def test_no_chunks_returns_zero(self, repo, parents):
        chat_session_id, _ = parents
        assert await repo.delete_by_chat_session(chat_session_id) == 0

    async def test_unknown_chat_session_returns_zero(self, repo):
        assert await repo.delete_by_chat_session(uuid.uuid4()) == 0

    async def test_second_delete_returns_zero(self, repo, parents):
        chat_session_id, document_id = parents
        await _seed(repo, chat_session_id, document_id, 2)

        assert await repo.delete_by_chat_session(chat_session_id) == 2
        assert await repo.delete_by_chat_session(chat_session_id) == 0


class TestDeleteByDocument:
    async def test_deletes_all_chunks_and_returns_count(self, repo, session, parents):
        chat_session_id, document_id = parents
        await _seed(repo, chat_session_id, document_id, 4)

        assert await repo.delete_by_document(document_id) == 4
        assert await _ids(session, document_id=document_id) == set()

    async def test_leaves_other_documents_in_same_session_untouched(
        self, repo, session, parents
    ):
        chat_session_id, document_id = parents
        _, other_document = await _parents(session, chat_session_id)
        await _seed(repo, chat_session_id, document_id, 2)
        survivors = await _seed(repo, chat_session_id, other_document, 3)

        await repo.delete_by_document(document_id)

        assert await _ids(session, document_id=other_document) == {
            c.id for c in survivors
        }

    async def test_parent_rows_are_kept(self, repo, session, parents):
        chat_session_id, document_id = parents
        await _seed(repo, chat_session_id, document_id, 2)

        await repo.delete_by_document(document_id)

        assert await _row_exists(session, "chat_sessions", chat_session_id)
        assert await _row_exists(session, "documents", document_id)

    async def test_no_chunks_returns_zero(self, repo, parents):
        _, document_id = parents
        assert await repo.delete_by_document(document_id) == 0

    async def test_unknown_document_returns_zero(self, repo):
        assert await repo.delete_by_document(uuid.uuid4()) == 0

    async def test_second_delete_returns_zero(self, repo, parents):
        chat_session_id, document_id = parents
        await _seed(repo, chat_session_id, document_id, 2)

        assert await repo.delete_by_document(document_id) == 2
        assert await repo.delete_by_document(document_id) == 0


class TestGetCandidateChunkEmbeddings:
    async def test_returns_all_chunks_for_chat_session(self, repo, parents):
        chat_session_id, document_id = parents
        seeded = await _seed(repo, chat_session_id, document_id, 3)

        result = await repo.get_candidate_chunk_embeddings(chat_session_id)

        assert {c.id for c in result} == {c.id for c in seeded}
        assert all(isinstance(c, ChunkEmbedding) for c in result)

    async def test_returns_chunks_across_documents(self, repo, session, parents):
        chat_session_id, first_document = parents
        _, second_document = await _parents(session, chat_session_id)
        first = await _seed(repo, chat_session_id, first_document, 2)
        second = await _seed(repo, chat_session_id, second_document, 2)

        result = await repo.get_candidate_chunk_embeddings(chat_session_id)

        assert {c.id for c in result} == {c.id for c in first + second}

    async def test_excludes_other_chat_sessions(self, repo, session, parents):
        chat_session_id, document_id = parents
        other_chat_session, other_document = await _parents(session)
        mine = await _seed(repo, chat_session_id, document_id, 2)
        await _seed(repo, other_chat_session, other_document, 3)

        result = await repo.get_candidate_chunk_embeddings(chat_session_id)

        assert {c.id for c in result} == {c.id for c in mine}

    async def test_returns_list_with_loaded_fields(self, repo, parents):
        chat_session_id, document_id = parents
        await repo.create_many([_chunk(chat_session_id, document_id, index=2)])

        result = await repo.get_candidate_chunk_embeddings(chat_session_id)

        assert isinstance(result, list)
        assert result[0].chunk_text == "chunk 2"
        assert result[0].chunk_index == 2
        assert [float(v) for v in result[0].embedding] == pytest.approx(
            _vector(2), rel=1e-4
        )

    async def test_no_chunks_returns_empty_list(self, repo, parents):
        chat_session_id, _ = parents
        assert await repo.get_candidate_chunk_embeddings(chat_session_id) == []

    async def test_unknown_chat_session_returns_empty_list(self, repo):
        assert await repo.get_candidate_chunk_embeddings(uuid.uuid4()) == []

    async def test_returns_every_chunk_without_a_limit(self, repo, parents):
        chat_session_id, document_id = parents
        await _seed(repo, chat_session_id, document_id, 150)

        assert len(await repo.get_candidate_chunk_embeddings(chat_session_id)) == 150

    async def test_deleted_chunks_are_not_returned(self, repo, parents):
        chat_session_id, document_id = parents
        await _seed(repo, chat_session_id, document_id, 3)
        await repo.delete_by_document(document_id)

        assert await repo.get_candidate_chunk_embeddings(chat_session_id) == []


class TestSearchBySimilarity:
    async def test_returns_most_similar_first(self, repo, completed_parents):
        chat_session_id, document_id = completed_parents
        low, high, middle = await _seed_similar(
            repo, chat_session_id, document_id, [0.5, 0.9, 0.7]
        )

        result = await repo.search_by_similarity(chat_session_id, QUERY, 0.0, 10)

        assert [c.id for c in result] == [high.id, middle.id, low.id]

    async def test_excludes_chunks_below_min_similarity(self, repo, completed_parents):
        chat_session_id, document_id = completed_parents
        _, kept, also_kept = await _seed_similar(
            repo, chat_session_id, document_id, [0.2, 0.6, 0.8]
        )

        result = await repo.search_by_similarity(chat_session_id, QUERY, 0.5, 10)

        assert {c.id for c in result} == {kept.id, also_kept.id}

    async def test_returns_at_most_limit_most_similar(self, repo, completed_parents):
        chat_session_id, document_id = completed_parents
        chunks = await _seed_similar(
            repo, chat_session_id, document_id, [0.5, 0.6, 0.7, 0.8, 0.9]
        )

        result = await repo.search_by_similarity(chat_session_id, QUERY, 0.0, 2)

        assert [c.id for c in result] == [chunks[4].id, chunks[3].id]

    async def test_returns_chunks_across_completed_documents(
        self, repo, session, completed_parents
    ):
        chat_session_id, first_document = completed_parents
        _, second_document = await _completed_parents(session, chat_session_id)
        first = await _seed_similar(repo, chat_session_id, first_document, [0.8])
        second = await _seed_similar(repo, chat_session_id, second_document, [0.9])

        result = await repo.search_by_similarity(chat_session_id, QUERY, 0.0, 10)

        assert [c.id for c in result] == [second[0].id, first[0].id]

    async def test_excludes_other_chat_sessions(
        self, repo, session, completed_parents
    ):
        chat_session_id, document_id = completed_parents
        other_chat_session, other_document = await _completed_parents(session)
        mine = await _seed_similar(repo, chat_session_id, document_id, [0.6])
        await _seed_similar(repo, other_chat_session, other_document, [0.9, 0.95])

        result = await repo.search_by_similarity(chat_session_id, QUERY, 0.0, 10)

        assert [c.id for c in result] == [mine[0].id]

    @pytest.mark.parametrize(
        "status",
        [s for s in DocumentStatus if s is not DocumentStatus.COMPLETED],
    )
    async def test_excludes_documents_that_are_not_completed(
        self, repo, session, completed_parents, status
    ):
        chat_session_id, completed_document = completed_parents
        _, other_document = await _parents(session, chat_session_id)
        await _set_status(session, other_document, status)
        completed = await _seed_similar(
            repo, chat_session_id, completed_document, [0.6]
        )
        await _seed_similar(repo, chat_session_id, other_document, [0.9])

        result = await repo.search_by_similarity(chat_session_id, QUERY, 0.0, 10)

        assert [c.id for c in result] == [completed[0].id]

    async def test_finds_chunks_when_other_sessions_are_closer(
        self, repo, session, completed_parents
    ):
        chat_session_id, document_id = completed_parents
        other_chat_session, other_document = await _completed_parents(session)
        await _seed_similar(repo, other_chat_session, other_document, [0.99] * 200)
        mine = await _seed_similar(
            repo, chat_session_id, document_id, [0.5, 0.6, 0.7]
        )

        result = await repo.search_by_similarity(chat_session_id, QUERY, 0.0, 10)

        assert [c.id for c in result] == [c.id for c in reversed(mine)]

    async def test_returns_list_with_loaded_fields(self, repo, completed_parents):
        chat_session_id, document_id = completed_parents
        await repo.create_many(
            [_chunk(chat_session_id, document_id, 2, _similar_to_query(0.8))]
        )

        result = await repo.search_by_similarity(chat_session_id, QUERY, 0.0, 10)

        assert isinstance(result, list)
        assert result[0].chunk_text == "chunk 2"
        assert result[0].chunk_index == 2
        assert [float(v) for v in result[0].embedding] == pytest.approx(
            _similar_to_query(0.8), abs=1e-6
        )

    async def test_no_chunks_returns_empty_list(self, repo, completed_parents):
        chat_session_id, _ = completed_parents
        assert await repo.search_by_similarity(chat_session_id, QUERY, 0.0, 10) == []

    async def test_unknown_chat_session_returns_empty_list(self, repo):
        assert await repo.search_by_similarity(uuid.uuid4(), QUERY, 0.0, 10) == []

    async def test_deleted_chunks_are_not_returned(self, repo, completed_parents):
        chat_session_id, document_id = completed_parents
        await _seed_similar(repo, chat_session_id, document_id, [0.6, 0.7])
        await repo.delete_by_document(document_id)

        assert await repo.search_by_similarity(chat_session_id, QUERY, 0.0, 10) == []

    async def test_wrong_query_dimension_raises(self, repo, completed_parents):
        chat_session_id, document_id = completed_parents
        await _seed_similar(repo, chat_session_id, document_id, [0.6])

        with pytest.raises(ApiException) as exc:
            await repo.search_by_similarity(
                chat_session_id, [1.0] * (DIMENSIONS + 1), 0.0, 10
            )
        assert exc.value.status_code == INTERNAL_ERROR


CALLS = {
    "create_many": lambda r: r.create_many([_chunk(uuid.uuid4(), uuid.uuid4())]),
    "delete_by_chat_session": lambda r: r.delete_by_chat_session(uuid.uuid4()),
    "delete_by_document": lambda r: r.delete_by_document(uuid.uuid4()),
    "get_candidate_chunk_embeddings": lambda r: r.get_candidate_chunk_embeddings(
        uuid.uuid4()
    ),
    "search_by_similarity": lambda r: r.search_by_similarity(
        uuid.uuid4(), QUERY, 0.0, 10
    ),
}

ERRORS = [
    (SQLAlchemyError("boom"), INTERNAL_ERROR),
    (OperationalError("SELECT 1", {}, Exception("connection lost")), UNAVAILABLE),
    (SATimeoutError("pool exhausted"), UNAVAILABLE),
]


class TestDatabaseFailures:
    @pytest.mark.parametrize("method", list(CALLS))
    @pytest.mark.parametrize("error, expected_status", ERRORS)
    async def test_failure_maps_to_status(
        self, repo, session, method, error, expected_status
    ):
        with patch.object(
            session, "execute", AsyncMock(side_effect=error)
        ), patch.object(session, "flush", AsyncMock(side_effect=error)):
            with pytest.raises(ApiException) as exc:
                await CALLS[method](repo)

        assert exc.value.status_code == expected_status
