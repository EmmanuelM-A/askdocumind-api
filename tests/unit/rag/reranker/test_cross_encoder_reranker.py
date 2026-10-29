"""
Unit tests for CrossEncoderReranker.

A fake stands in for the CrossEncoder class, so no model is downloaded or run.
The fake records how it is created and called, including the thread, so the
tests check that loading and scoring stay off the event loop.

Error tests assert only the HTTP status code of the raised ApiException.
"""

import asyncio
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from src.exceptions.base import ApiException
from src.rag.services.rerank import cross_encoder_reranker as reranker_module
from src.rag.services.rerank.cross_encoder_reranker import (
    CrossEncoderReranker,
    CrossEncoderRerankerConfig,
)

# ---------------------------------------------------------------------------
# Fakes and helpers
# ---------------------------------------------------------------------------


class FakeEncoder:
    """
    Replaces the CrossEncoder class. Calling it creates the model, and the
    same object then acts as the model. Scores come from a text-to-score
    dict, or from the text length when no dict is given.
    """

    def __init__(self, scores=None, load_error=None, predict_error=None, delay=0.0):
        self._scores = scores
        self._load_error = load_error
        self._predict_error = predict_error
        self._delay = delay
        self._lock = threading.Lock()
        self._active = 0
        self.max_active = 0
        self.created = []
        self.create_threads = []
        self.predict_calls = []
        self.predict_threads = []

    def __call__(self, model_name_or_path, max_length):
        self.created.append(
            {"model_name_or_path": model_name_or_path, "max_length": max_length}
        )
        self.create_threads.append(threading.get_ident())
        time.sleep(self._delay)
        if self._load_error:
            raise self._load_error
        return self

    def predict(self, pairs, batch_size, show_progress_bar):
        self.predict_calls.append(
            {
                "pairs": pairs,
                "batch_size": batch_size,
                "show_progress_bar": show_progress_bar,
            }
        )
        self.predict_threads.append(threading.get_ident())

        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        time.sleep(self._delay)
        with self._lock:
            self._active -= 1

        if self._predict_error:
            raise self._predict_error
        if self._scores is None:
            return np.array([len(text) for _, text in pairs], dtype=np.float32)
        return np.array([self._scores[text] for _, text in pairs], dtype=np.float32)


@pytest.fixture
def install_encoder(monkeypatch):
    def _install(**kwargs) -> FakeEncoder:
        fake = FakeEncoder(**kwargs)
        monkeypatch.setattr(reranker_module, "CrossEncoder", fake)
        return fake

    return _install


def make_reranker(**overrides) -> CrossEncoderReranker:
    config = {"model_name": "test-model", "max_length": 256, **overrides}
    return CrossEncoderReranker(CrossEncoderRerankerConfig(**config))


def make_chunks(*texts):
    return [SimpleNamespace(chunk_text=text) for text in texts]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestConfig:

    def test_batch_size_defaults_to_32(self):
        config = CrossEncoderRerankerConfig(model_name="m", max_length=128)

        assert config.batch_size == 32

    @pytest.mark.parametrize(
        "values",
        [
            {"model_name": "   ", "max_length": 128},
            {"model_name": "m", "max_length": 0},
            {"model_name": "m", "max_length": -1},
            {"model_name": "m", "max_length": 128, "batch_size": 0},
        ],
    )
    def test_invalid_values_are_rejected(self, values):
        with pytest.raises(ValidationError):
            CrossEncoderRerankerConfig(**values)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


class TestRanking:

    @pytest.mark.asyncio
    async def test_chunks_come_back_by_descending_score(self, install_encoder):
        install_encoder(scores={"low": 0.1, "high": 0.9, "mid": 0.5})
        chunks = make_chunks("low", "high", "mid")
        original = list(chunks)

        result = await make_reranker().rerank("question", chunks)

        assert [c.chunk_text for c in result] == ["high", "mid", "low"]
        assert all(any(r is c for c in original) for r in result)
        assert chunks == original

    @pytest.mark.asyncio
    async def test_equal_scores_keep_their_original_order(self, install_encoder):
        install_encoder(scores={"a": 0.5, "b": 0.5, "c": 0.5, "d": 0.9})

        result = await make_reranker().rerank(
            "question", make_chunks("a", "b", "c", "d")
        )

        assert [c.chunk_text for c in result] == ["d", "a", "b", "c"]

    @pytest.mark.asyncio
    async def test_nan_scores_are_ranked_last(self, install_encoder):
        install_encoder(scores={"a": float("nan"), "b": 0.2, "c": 0.8})

        result = await make_reranker().rerank("question", make_chunks("a", "b", "c"))

        assert [c.chunk_text for c in result] == ["c", "b", "a"]

    @pytest.mark.asyncio
    async def test_the_model_scores_the_stripped_query_against_each_chunk(
        self, install_encoder
    ):
        fake = install_encoder()

        await make_reranker().rerank("  what is rag?\n", make_chunks("one", "two"))

        assert fake.predict_calls[0]["pairs"] == [
            ["what is rag?", "one"],
            ["what is rag?", "two"],
        ]

    @pytest.mark.asyncio
    async def test_config_values_reach_the_model(self, install_encoder):
        fake = install_encoder()
        reranker = make_reranker(model_name="my-model", max_length=384, batch_size=8)

        await reranker.rerank("question", make_chunks("one"))

        assert fake.created == [{"model_name_or_path": "my-model", "max_length": 384}]
        assert fake.predict_calls[0]["batch_size"] == 8
        assert fake.predict_calls[0]["show_progress_bar"] is False


# ---------------------------------------------------------------------------
# Input handling
# ---------------------------------------------------------------------------


class TestInput:

    @pytest.mark.asyncio
    async def test_no_chunks_return_an_empty_list_without_loading_the_model(
        self, install_encoder
    ):
        fake = install_encoder()

        result = await make_reranker().rerank("question", [])

        assert result == []
        assert fake.created == []

    @pytest.mark.asyncio
    async def test_a_blank_query_raises_422_without_loading_the_model(
        self, install_encoder
    ):
        fake = install_encoder()
        reranker = make_reranker()

        for query in ("", "   ", "\n\t"):
            with pytest.raises(ApiException) as exc_info:
                await reranker.rerank(query, make_chunks("one"))

            assert exc_info.value.status_code == 422

        assert fake.created == []


# ---------------------------------------------------------------------------
# Model lifecycle
# ---------------------------------------------------------------------------


class TestModelLifecycle:

    @pytest.mark.asyncio
    async def test_the_model_loads_on_first_use_and_is_reused(self, install_encoder):
        fake = install_encoder()
        reranker = make_reranker()
        assert fake.created == []

        await reranker.rerank("question", make_chunks("one"))
        await reranker.rerank("question", make_chunks("two"))

        assert len(fake.created) == 1
        assert len(fake.predict_calls) == 2

    @pytest.mark.asyncio
    async def test_concurrent_first_calls_load_the_model_once(self, install_encoder):
        fake = install_encoder(delay=0.05)
        reranker = make_reranker()

        await asyncio.gather(
            *(reranker.rerank("question", make_chunks("one")) for _ in range(5))
        )

        assert len(fake.created) == 1

    @pytest.mark.asyncio
    async def test_warm_up_loads_the_model_before_the_first_request(
        self, install_encoder
    ):
        fake = install_encoder()
        reranker = make_reranker()

        await reranker.warm_up()
        await reranker.warm_up()
        assert len(fake.created) == 1
        assert fake.predict_calls == []

        await reranker.rerank("question", make_chunks("one"))
        assert len(fake.created) == 1

    @pytest.mark.asyncio
    async def test_a_failed_load_is_retried_on_the_next_call(self, install_encoder):
        fake = install_encoder(load_error=OSError("offline"))
        reranker = make_reranker()

        with pytest.raises(ApiException):
            await reranker.rerank("question", make_chunks("one"))

        fake._load_error = None
        result = await reranker.rerank("question", make_chunks("one"))

        assert len(fake.created) == 2
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Threads and concurrency
# ---------------------------------------------------------------------------


class TestConcurrency:

    @pytest.mark.asyncio
    async def test_loading_and_scoring_run_off_the_event_loop_thread(
        self, install_encoder
    ):
        fake = install_encoder()
        loop_thread = threading.get_ident()

        await make_reranker().rerank("question", make_chunks("one"))

        assert fake.create_threads and fake.predict_threads
        assert loop_thread not in fake.create_threads
        assert loop_thread not in fake.predict_threads

    @pytest.mark.asyncio
    async def test_concurrent_requests_are_scored_one_at_a_time(self, install_encoder):
        fake = install_encoder(delay=0.03)
        reranker = make_reranker()

        await asyncio.gather(
            *(reranker.rerank("question", make_chunks("one", "two")) for _ in range(4))
        )

        assert len(fake.predict_calls) == 4
        assert fake.max_active == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:

    @pytest.mark.asyncio
    async def test_a_scoring_error_raises_500_with_its_cause(self, install_encoder):
        cause = RuntimeError("CUDA out of memory")
        install_encoder(predict_error=cause)

        with pytest.raises(ApiException) as exc_info:
            await make_reranker().rerank("question", make_chunks("one"))

        assert exc_info.value.status_code == 500
        assert exc_info.value.__cause__ is cause

    @pytest.mark.asyncio
    async def test_a_model_load_error_raises_500(self, install_encoder):
        install_encoder(load_error=OSError("model not found"))

        with pytest.raises(ApiException) as exc_info:
            await make_reranker().rerank("question", make_chunks("one"))

        assert exc_info.value.status_code == 500
