"""
Unit tests for where setup_logging sends logs in each environment.
"""

import logging
import sys

import pytest

from src.config.configs import settings
from src.config.logger import setup_logging


@pytest.fixture(autouse=True)
def _restore_logging():
    yield
    setup_logging()


def _stdout_handlers():
    return [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, logging.StreamHandler)
        and getattr(handler, "stream", None) is sys.stdout
    ]


@pytest.mark.parametrize("env", ["production", "staging", "test"])
def test_logs_go_to_stdout_outside_development(monkeypatch, env):
    monkeypatch.setattr(settings.server, "ENV", env)

    setup_logging()

    assert len(_stdout_handlers()) == 1


def test_development_logs_only_to_files(monkeypatch):
    monkeypatch.setattr(settings.server, "ENV", "development")

    setup_logging()

    assert _stdout_handlers() == []
