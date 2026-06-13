"""
Global exception handler for structured error responses and logging.
Handles both custom ApiException instances and unexpected errors.
"""

import traceback

from fastapi import Request, status, FastAPI, HTTPException
from starlette.responses import JSONResponse

from src.config.configs import settings
from src.logger.base_logger import BaseLogger
from src.errors.api_exceptions import ApiException
from src.api.utils.api_responses import ErrorInfo
from src.api.utils.api_responses import ErrorResponseModel
from src.api.utils.response_delivery import create_error_response

logger = BaseLogger(__name__)


async def api_exception_handler(request: Request, exc: ApiException) -> JSONResponse:
    """
    Handle all exceptions derived from ApiException (custom application errors).
    """

    error = ErrorInfo(
        code=exc.error.code,
        details=exc.error.details,
        stack_trace=exc.error.stack_trace if settings.app.ENV == "development" else None,
    )

    error_response_model = ErrorResponseModel(
        success=False, message=exc.detail, error=error
    )

    logger.error(
        f"APIException | path={request.url.path} | status={exc.status_code} | "
        f"code={exc.error.code} | details={exc.error.details or exc.detail}",
    )

    return create_error_response(
        status_code=exc.status_code, error_response_model=error_response_model
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI's built-in HTTPExceptions."""

    error = ErrorInfo(
        code="HTTP_EXCEPTION",
        details=str(exc.detail),
        stack_trace=traceback.format_exc() if settings.app.ENV == "development" else None,
    )

    error_response_model = ErrorResponseModel(
        success=False, message=str(exc.detail), error=error
    )

    logger.warning(
        f"HTTPException | path={request.url.path} | status={exc.status_code} | "
        f"detail={exc.detail}",
    )

    return create_error_response(
        status_code=exc.status_code, error_response_model=error_response_model
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unexpected runtime exceptions.
    """

    error = ErrorInfo(
        code="INTERNAL_SERVER_ERROR",
        details=str(exc),
        stack_trace=traceback.format_exc() if settings.app.ENV == "development" else None,
    )

    error_response_model = ErrorResponseModel(
        success=False,
        message="An unexpected error occurred.",
        error=error,
    )

    logger.error(
        f"UnhandledException | path={request.url.path} | error={str(exc)}",
    )

    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_response_model=error_response_model,
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Registers exception handlers to the application."""

    app.add_exception_handler(ApiException, api_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
