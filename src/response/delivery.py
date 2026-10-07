"""
Responsible for creating and sending standardized API responses for both
successful and failed requests.
"""

from datetime import datetime, timezone
from typing import Dict, TypeVar, Generic, Mapping

from fastapi.responses import JSONResponse
from pydantic import Field

from src.shared.utils import CamelCaseSerializer
from src.response.models import ErrorInfo

T = TypeVar("T")


class _SuccessResponse(CamelCaseSerializer, Generic[T]):
    """Pydantic model for a successful API response."""

    success: bool = Field(
        default=True, description="Indicates if the request was successful."
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="The timestamp of the response.",
    )

    message: str = Field(description="Success message for the response.")

    data: T | None = Field(
        default=None, description="Optional data to be included in the response."
    )


class _ErrorResponse(CamelCaseSerializer):
    """Pydantic model for a failed API response."""

    success: bool = Field(
        default=False, description="Indicates if the request was successful."
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="The timestamp of the response.",
    )

    message: str = Field(description="Error message for the response.")

    error: ErrorInfo = Field(description="An object containing error information.")


def send_success_response(
    message: str, status_code: int, data: T | None = None
) -> JSONResponse:
    """Creates and sends a standardized success response."""

    success_response_model = _SuccessResponse(message=message, data=data)

    return JSONResponse(
        status_code=status_code,
        content=success_response_model.model_dump(by_alias=True, mode="json"),
    )


def send_error_response(
    message: str,
    status_code: int,
    error_code: str,
    details: Dict[str, str] | None = None,
    stack_trace: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Creates and sends a standardized error response."""

    error_info = ErrorInfo(code=error_code, details=details, stack_trace=stack_trace)

    error_response_model = _ErrorResponse(message=message, error=error_info)

    return JSONResponse(
        status_code=status_code,
        content=error_response_model.model_dump(by_alias=True, mode="json"),
        headers=headers,
    )
