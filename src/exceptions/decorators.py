"""
Decorators for handling database-related exceptions in asynchronous functions.

These decorators catch specific SQLAlchemy exceptions and raise standardized
API exceptions with appropriate HTTP status codes and error messages. They
can be applied to any asynchronous function that interacts with the database
to ensure consistent error handling across the application.

IMPORTANT - The order of the decorators matters! General handlers like
`handle_sqlalchemy_exceptions` applied last (on top) with more specific
handlers like `handle_database_unavailable_exceptions` applied first
(closest to the function) to ensure that specific exceptions are caught and
handled appropriately before falling back to more general exception handler.
"""

import functools
from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec, TypeVar

from sqlalchemy.exc import (
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
    TimeoutError,
)

from src.exceptions import conflict_error, database_error, service_unavailable_error

P = ParamSpec("P")
R = TypeVar("R")

_AsyncFn = Callable[P, Coroutine[Any, Any, R]]


def handle_database_unavailable_exceptions(
    error_details: dict[str, str] | None = None,
    headers: dict | None = None,
) -> Callable[[_AsyncFn[P, R]], _AsyncFn[P, R]]:
    def decorator(func: _AsyncFn[P, R]) -> _AsyncFn[P, R]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return await func(*args, **kwargs)
            except (OperationalError, TimeoutError) as e:
                raise service_unavailable_error(
                    message="The database service is currently unavailable.",
                    error_code="DATABASE_UNAVAILABLE",
                    error_details=error_details,
                    cause=e,
                    headers=headers,
                ) from e

        return wrapper

    return decorator


def handle_database_integrity_exceptions(
    message: str,
    error_code: str,
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> Callable[[_AsyncFn[P, R]], _AsyncFn[P, R]]:
    def decorator(func: _AsyncFn[P, R]) -> _AsyncFn[P, R]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return await func(*args, **kwargs)
            except IntegrityError as e:
                raise conflict_error(
                    message=message,
                    error_code=error_code,
                    error_details=error_details,
                    cause=cause,
                    headers=headers,
                ) from e

        return wrapper

    return decorator


def handle_sqlalchemy_exceptions(
    message: str,
    error_code: str,
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> Callable[[_AsyncFn[P, R]], _AsyncFn[P, R]]:
    def decorator(func: _AsyncFn[P, R]) -> _AsyncFn[P, R]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return await func(*args, **kwargs)
            except SQLAlchemyError as e:
                raise database_error(
                    message=message,
                    error_code=error_code,
                    error_details=error_details,
                    cause=cause,
                    headers=headers,
                ) from e

        return wrapper

    return decorator
