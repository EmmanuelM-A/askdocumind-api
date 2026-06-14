"""Tests for the anonymous user session cleanup scheduler."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.config.configs import settings


@pytest.mark.asyncio
async def test_run_scheduler_calls_cleanup_until_stop_event_is_set():
    """Scheduler calls delete_expired_anonymous_user_sessions each iteration."""
    from src.api.services.cleanup.cleanup_resources import _run_scheduler

    stop_event = asyncio.Event()
    call_count = 0

    async def _fake_cleanup():
        nonlocal call_count
        call_count += 1
        stop_event.set()

    service = Mock()
    service.delete_expired_anonymous_user_sessions = _fake_cleanup

    await _run_scheduler(service, stop_event, interval_minutes=1)

    assert call_count == 1


@pytest.mark.asyncio
async def test_run_scheduler_does_not_run_when_stop_event_already_set():
    """Scheduler exits immediately if the stop event is already set on entry."""
    from src.api.services.cleanup.cleanup_resources import _run_scheduler

    stop_event = asyncio.Event()
    stop_event.set()

    service = Mock()
    service.delete_expired_anonymous_user_sessions = AsyncMock()

    await _run_scheduler(service, stop_event, interval_minutes=1)

    service.delete_expired_anonymous_user_sessions.assert_not_called()


@pytest.mark.asyncio
async def test_init_cleanup_returns_early_when_disabled(monkeypatch: pytest.MonkeyPatch):
    """init_anon_user_sessions_cleanup should no-op when CLEANUP_ENABLED is False."""
    from src.api.services.cleanup.cleanup_resources import init_anon_user_sessions_cleanup

    monkeypatch.setattr(settings.anon, "CLEANUP_ENABLED", False)

    with patch(
        "src.api.services.cleanup.cleanup_resources._run_scheduler"
    ) as mock_scheduler:
        await init_anon_user_sessions_cleanup()

    mock_scheduler.assert_not_called()


@pytest.mark.asyncio
async def test_init_cleanup_passes_configured_interval_to_scheduler(
    monkeypatch: pytest.MonkeyPatch,
):
    """init_anon_user_sessions_cleanup converts CLEANUP_INTERVAL_H to minutes."""
    from src.api.services.cleanup.cleanup_resources import init_anon_user_sessions_cleanup

    monkeypatch.setattr(settings.anon, "CLEANUP_ENABLED", True)
    monkeypatch.setattr(settings.anon, "CLEANUP_INTERVAL_H", 2)

    stop_event = asyncio.Event()
    stop_event.set()

    fake_service = Mock()
    fake_service.delete_expired_anonymous_user_sessions = AsyncMock()

    with patch(
        "src.api.services.cleanup.cleanup_resources.get_anonymous_user_service",
        return_value=fake_service,
    ), patch(
        "src.api.services.cleanup.cleanup_resources._run_scheduler",
        new_callable=AsyncMock,
    ) as mock_scheduler:
        await init_anon_user_sessions_cleanup(stop_event=stop_event)

    mock_scheduler.assert_awaited_once_with(
        anonymous_user_services=fake_service,
        stop_event=stop_event,
        interval_minutes=120,
    )
