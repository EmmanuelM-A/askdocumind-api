"""
Custom base error class for API exceptions.

This class is used throughout the API to raise structured, JSON-based
errors that integrate seamlessly with FastAPI’s exception handling.
"""

from typing import Optional

from fastapi import HTTPException
from starlette import status

from src.utils.api_responses import ErrorInfo


class ApiException(HTTPException):
    """
    Custom base exception for API errors.

    Provides a structured JSON error response using Pydantic models,
    while remaining compatible with FastAPI's built-in exception handling.
    """

    def __init__(
        self,
        error_code: str,
        error_details: Optional[str] = None,
        stack_trace: Optional[str] = None,
        message: str = "An unexpected error occurred.",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        headers: Optional[dict] = None,
    ) -> None:
        self.error = ErrorInfo(
            code=error_code, details=error_details, stack_trace=stack_trace
        )

        super().__init__(
            status_code=status_code,
            detail=message,
            headers=headers,
        )
