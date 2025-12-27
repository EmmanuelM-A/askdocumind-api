"""
Responsible for sending the http response objects to users using the standardized
response format.
"""

from starlette.responses import JSONResponse

from src.utils.api_responses import SuccessResponseModel, ErrorResponseModel


def create_success_response(
    status_code: int, success_response_model: SuccessResponseModel
) -> JSONResponse:
    """Sets the status code and sends a standardized success response."""

    return JSONResponse(
        status_code=status_code,
        content=success_response_model.model_dump(mode="json"),
    )


def create_error_response(
    status_code: int, error_response_model: ErrorResponseModel
) -> JSONResponse:
    """Sets the status code and sends a standardized error response."""

    return JSONResponse(
        status_code=status_code, content=error_response_model.model_dump(mode="json")
    )
