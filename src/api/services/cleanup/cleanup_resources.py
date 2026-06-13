"""Cleanup orchestration for expired anonymous user sessions."""

import asyncio

from src.api.services.auth.anonymous_user import AnonymousUserSessionService
from src.api.services.service_factory import get_anonymous_user_service
from src.config.configs import settings
from src.logger.base_logger import BaseLogger

_logger = BaseLogger(__name__)

async def _run_scheduler(
    anonymous_user_services: AnonymousUserSessionService,
    stop_event: asyncio.Event,
    interval_minutes: int,
) -> None:
    """Run cleanup repeatedly until the stop event is set."""

    sleep_seconds = max(interval_minutes * 60, 1)

    while not stop_event.is_set():
        await anonymous_user_services.delete_expired_anonymous_user_sessions()

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=sleep_seconds)
        except asyncio.TimeoutError:
            continue
    
    _logger.info("Anonymous user session cleanup scheduler stopped.")


async def init_anon_user_sessions_cleanup(
    stop_event: asyncio.Event | None = None,
    interval_minutes: int | None = None,
) -> None:
    """
    Start the cleanup scheduler, running until the stop event is set.
    """

    if not settings.anon.CLEANUP_ENABLED:
        _logger.info("Anonymous user session cleanup is disabled in settings.")
        return

    stop_event = stop_event or asyncio.Event()
    interval_minutes = (
        interval_minutes or
        settings.anon.CLEANUP_INTERVAL_H * 60
    )

    await _run_scheduler(
        anonymous_user_services=get_anonymous_user_service(),
        stop_event=stop_event,
        interval_minutes=interval_minutes,
    )
