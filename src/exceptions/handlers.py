"""
Global exception handlers for structured error responses and logging.
"""

import logging
import traceback

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.config.configs import settings
from src.exceptions.base import ApiException
from src.response.delivery import send_error_response

_logger = logging.getLogger(__name__)


def _stack_trace(exc: BaseException) -> str | None:
    """Return the formatted traceback in development only."""
    if settings.server.ENV != "development":
        return None
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def _log(request: Request, status_code: int, message: str, exc: BaseException) -> None:
    """Log 5xx at ERROR with a traceback, and 4xx at WARNING."""
    is_server_error = status_code >= 500
    _logger.log(
        logging.ERROR if is_server_error else logging.WARNING,
        "%s %s | status: %s | message: %s",
        request.method,
        request.url.path,
        status_code,
        message,
        exc_info=exc if (is_server_error or exc.__cause__) else None,
    )


async def _api_exception_handler(request: Request, exc: ApiException) -> JSONResponse:
    message = str(exc.detail)
    _log(request, exc.status_code, message, exc)

    return send_error_response(
        message=message,
        status_code=exc.status_code,
        error_code=exc.error_code,
        details=exc.error_details,
        stack_trace=_stack_trace(exc),
        headers=exc.headers,
    )


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    message = str(exc.detail)
    _log(request, exc.status_code, message, exc)

    return send_error_response(
        message=message,
        status_code=exc.status_code,
        error_code=f"HTTP_{exc.status_code}",
        stack_trace=_stack_trace(exc),
        headers=getattr(exc, "headers", None),
    )


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = {
        ".".join(str(part) for part in error["loc"]): error["msg"]
        for error in exc.errors()
    }
    _log(request, 422, "Request validation failed", exc)

    return send_error_response(
        message="Request validation failed.",
        status_code=422,
        error_code="VALIDATION_ERROR",
        details=details,
    )


async def _unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    _log(request, status.HTTP_500_INTERNAL_SERVER_ERROR, "Unhandled exception", exc)

    return send_error_response(
        message="An unexpected error occurred.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code="UNHANDLED_EXCEPTION",
        stack_trace=_stack_trace(exc),
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Registers exception handlers on the application."""
    app.add_exception_handler(ApiException, _api_exception_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
