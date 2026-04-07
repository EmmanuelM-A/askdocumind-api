"""
This module defines custom responses for handling API responses.
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict, field_serializer

from src.utils import format_datetime


class ResponseModel(BaseModel):
    """Base Pydantic model for all responses."""

    # Use a field serializer for timestamp to replace deprecated json_encoders
    model_config = ConfigDict()

    success: bool = Field(description="Indicates if the request was successful.")

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="The timestamp of the response.",
    )

    message: str = Field(description="Success message for the response.")

    @field_serializer("timestamp")
    def serialize_timestamp(self, v: datetime, _info):
        """Serialize timestamp to a human-readable string."""
        return format_datetime(v)


class SuccessResponseModel(ResponseModel):
    """Pydantic model for successful responses."""

    success: bool = Field(
        default=True, description="Indicates if the request was successful."
    )

    data: Optional[Any] = Field(
        default=None, description="Optional data to be included in the response."
    )


class ErrorInfo(BaseModel):
    """Pydantic model for detailed error information."""

    code: str = Field(description="Error code representing the type of error.")

    details: Optional[str] = Field(default=None, description="Detailed error message.")

    stack_trace: Optional[str] = Field(
        default=None, description="Optional stack trace for debugging purposes."
    )


class ErrorResponseModel(ResponseModel):
    """Pydantic model for error responses."""

    success: bool = Field(
        default=False, description="Indicates if the request was successful."
    )

    error: ErrorInfo = Field(description="An object containing error information.")


class CustomJSONEncoder(json.JSONEncoder):
    """
    Responsible for converting custom JSON response classes into a
    suitable format.
    """

    def default(self, obj):
        """
        Convert custom objects to a serializable format.
        """

        if isinstance(obj, datetime):
            return format_datetime(obj)

        if hasattr(obj, "to_json"):
            return json.loads(obj.to_json())

        if hasattr(obj, "to_dict"):
            return obj.to_dict()

        return str(obj)  # Fallback to string representation


def ensure_serializable(data):
    """Ensures data is JSON serializable, converting when necessary."""

    try:
        json.dumps(data, cls=CustomJSONEncoder)
        return data
    except TypeError:
        return json.loads(json.dumps(str(data)))
