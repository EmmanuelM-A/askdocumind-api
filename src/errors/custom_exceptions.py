"""
This module defines helper functions for throwing standardized API exceptions.
Each function raises an ApiException with a specific HTTP status code and
consistent structure for error handling across the API.
"""

from typing import Optional
from fastapi import status

from src.errors.api_exceptions import ApiException


def bad_request_error(
    message: str,
    error_code: str,
    error_details: Optional[str] = None,
    stack_trace: Optional[str] = None,
    headers: Optional[dict] = None,
) -> ApiException:
    """Raises a 400 Bad Request exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        stack_trace=stack_trace,
        message=message,
        status_code=status.HTTP_400_BAD_REQUEST,
        headers=headers,
    )


def unauthorized_error(
    message: str = "Unauthorized access.",
    error_code: str = "UNAUTHORIZED",
    error_details: Optional[str] = None,
    stack_trace: Optional[str] = None,
    headers: Optional[dict] = None,
) -> ApiException:
    """Raises a 401 Unauthorized exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        stack_trace=stack_trace,
        message=message,
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers=headers,
    )


def forbidden_error(
    message: str = "Forbidden: insufficient permissions.",
    error_code: str = "FORBIDDEN",
    error_details: Optional[str] = None,
    stack_trace: Optional[str] = None,
    headers: Optional[dict] = None,
) -> ApiException:
    """Raises a 403 Forbidden exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        stack_trace=stack_trace,
        message=message,
        status_code=status.HTTP_403_FORBIDDEN,
        headers=headers,
    )


def not_found_error(
    message: str = "Requested resource not found.",
    error_code: str = "NOT_FOUND",
    error_details: Optional[str] = None,
    stack_trace: Optional[str] = None,
    headers: Optional[dict] = None,
) -> ApiException:
    """Raises a 404 Not Found exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        stack_trace=stack_trace,
        message=message,
        status_code=status.HTTP_404_NOT_FOUND,
        headers=headers,
    )


def conflict_error(
    message: str = "Resource conflict occurred.",
    error_code: str = "CONFLICT",
    error_details: Optional[str] = None,
    stack_trace: Optional[str] = None,
    headers: Optional[dict] = None,
) -> ApiException:
    """Raises a 409 Conflict exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        stack_trace=stack_trace,
        message=message,
        status_code=status.HTTP_409_CONFLICT,
        headers=headers,
    )


def unprocessable_entity_error(
    message: str = "Unprocessable entity.",
    error_code: str = "UNPROCESSABLE_ENTITY",
    error_details: Optional[str] = None,
    stack_trace: Optional[str] = None,
    headers: Optional[dict] = None,
) -> ApiException:
    """Raises a 422 Unprocessable Entity exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        stack_trace=stack_trace,
        message=message,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        headers=headers,
    )


def database_error(
    message: str = "An error occurred in the database",
    error_code: str = "INTERNAL_SERVER_ERROR",
    error_details: Optional[str] = None,
    stack_trace: Optional[str] = None,
    headers: Optional[dict] = None,
) -> ApiException:
    """Raises a 500 Internal Server Error exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        stack_trace=stack_trace,
        message=message,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        headers=headers,
    )


def server_error(
    message: str = "An internal server error occurred.",
    error_code: str = "INTERNAL_SERVER_ERROR",
    error_details: Optional[str] = None,
    stack_trace: Optional[str] = None,
    headers: Optional[dict] = None,
) -> ApiException:
    """Raises a 500 Internal Server Error exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        stack_trace=stack_trace,
        message=message,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        headers=headers,
    )
