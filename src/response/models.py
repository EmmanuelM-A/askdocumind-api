"""
This module defines Pydantic models for API response structures, including
error information.
"""

from pydantic import Field

from src.shared.utils import CamelCaseSerializer


class ErrorInfo(CamelCaseSerializer):
    """Pydantic model for error information in API responses."""

    code: str = Field(description="Error code representing the type of error.")

    details: dict[str, str] | None = Field(
        default=None, description="Optional additional details about the error."
    )

    stack_trace: str | None = Field(
        default=None, description="Optional stack trace for debugging purposes."
    )
