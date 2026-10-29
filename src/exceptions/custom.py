"""
This module defines helper functions for throwing standardized API exceptions.
Each function raises an ApiException with a specific HTTP status code and
consistent structure for error handling across the API.
"""

from fastapi import status

from src.exceptions.base import ApiException


def bad_request_error(
    message: str,
    error_code: str = "BAD_REQUEST",
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> ApiException:
    """Raises a 400 Bad Request exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        message=message,
        status_code=status.HTTP_400_BAD_REQUEST,
        headers=headers,
        cause=cause,
    )


def unauthorized_error(
    message: str,
    error_code: str = "UNAUTHORIZED",
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> ApiException:
    """Raises a 401 Unauthorized exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        message=message,
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers=headers,
        cause=cause,
    )


def forbidden_error(
    message: str,
    error_code: str = "FORBIDDEN",
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> ApiException:
    """Raises a 403 Forbidden exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        message=message,
        status_code=status.HTTP_403_FORBIDDEN,
        headers=headers,
        cause=cause,
    )


def not_found_error(
    message: str,
    error_code: str = "NOT_FOUND",
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> ApiException:
    """Raises a 404 Not Found exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        message=message,
        status_code=status.HTTP_404_NOT_FOUND,
        headers=headers,
        cause=cause,
    )


def conflict_error(
    message: str,
    error_code: str = "CONFLICT",
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> ApiException:
    """Raises a 409 Conflict exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        message=message,
        status_code=status.HTTP_409_CONFLICT,
        headers=headers,
        cause=cause,
    )


def unprocessable_content_error(
    message: str,
    error_code: str = "UNPROCESSABLE_CONTENT",
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> ApiException:
    """Raises a 422 Unprocessable Entity exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        message=message,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        headers=headers,
        cause=cause,
    )


def database_error(
    message: str,
    error_code: str = "DATABASE_ERROR",
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> ApiException:
    """Raises a 500 Internal Server Error exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        message=message,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        headers=headers,
        cause=cause,
    )


def server_error(
    message: str,
    error_code: str = "SERVER_ERROR",
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> ApiException:
    """Raises a 500 Internal Server Error exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        message=message,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        headers=headers,
        cause=cause,
    )


def object_storage_error(
    message: str,
    error_code: str = "OBJECT_STORAGE_ERROR",
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> ApiException:
    """Raises a 500 Internal Server Error exception specifically for object
    storage issues."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        message=message,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        headers=headers,
        cause=cause,
    )


def service_unavailable_error(
    message: str,
    error_code: str = "SERVICE_UNAVAILABLE",
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> ApiException:
    """Raises a 503 Service Unavailable exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        message=message,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        headers=headers,
        cause=cause,
    )


def validation_error(
    message: str,
    error_code: str = "VALIDATION_ERROR",
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> ApiException:
    """Raises a 422 Unprocessable Entity exception for validation errors."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        message=message,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        headers=headers,
        cause=cause,
    )


def content_too_large_error(
    message: str,
    error_code: str = "CONTENT_TOO_LARGE",
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> ApiException:
    """Raises a 413 Payload Too Large exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        message=message,
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        headers=headers,
        cause=cause,
    )


def unsupported_media_type_error(
    message: str,
    error_code: str = "UNSUPPORTED_MEDIA_TYPE",
    error_details: dict[str, str] | None = None,
    cause: BaseException | None = None,
    headers: dict | None = None,
) -> ApiException:
    """Raises a 415 Unsupported Media Type exception."""
    return ApiException(
        error_code=error_code,
        error_details=error_details,
        message=message,
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        headers=headers,
        cause=cause,
    )
