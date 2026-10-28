from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    status,
    Request,
    UploadFile,
    File,
    Query,
    Depends,
)
from starlette.responses import JSONResponse

from src.database.utils import Pagination
from src.middleware.rate_limiter import default_limit, uploads_limit
from src.response.delivery import send_success_response
from src.uploads.dependencies import get_upload_service, get_ingestion_runner
from src.uploads.schemas.upload import DeleteUploadedFilesRequest
from src.uploads.services.ingestion_service import IngestionRunner, build_job
from src.uploads.services.upload_service import UploadService

upload_router = APIRouter(prefix="/uploads", tags=["Uploads"])


@upload_router.post(
    path="/{chat_session_id}",
    summary="Upload a file to a specific chat session",
    status_code=status.HTTP_202_ACCEPTED,
)
@uploads_limit
async def upload_file(
    request: Request,
    chat_session_id: UUID,
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    runner: Annotated[IngestionRunner, Depends(get_ingestion_runner)],
    file: UploadFile = File(...),
) -> JSONResponse:
    """
    Upload a file to a specific chat session and initiate the ingestion
    process.
    """
    document = await upload_service.upload(
        chat_session_id=chat_session_id,
        user_id=request.state.user_id,
        file=file,
    )

    runner.start(build_job(document))

    return send_success_response(
        message="File uploaded successfully.",
        status_code=status.HTTP_202_ACCEPTED,
        data=document.viewable(),
    )


@upload_router.get(
    path="/{chat_session_id}",
    summary="Get the list of uploaded files for a specific chat session",
    status_code=status.HTTP_200_OK,
)
@uploads_limit
async def get_uploaded_files(
    request: Request,
    chat_session_id: UUID,
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    paginate: Annotated[Pagination, Query()],
) -> JSONResponse:
    """
    Retrieve the list of uploaded files for a specific chat session.
    """
    documents = await upload_service.get_uploaded_files(
        chat_session_id=chat_session_id,
        user_id=request.state.user_id,
        paginate=paginate,
    )

    return send_success_response(
        message="Uploaded files retrieved successfully.",
        status_code=status.HTTP_200_OK,
        data=documents,
    )


@upload_router.get(
    path="/{chat_session_id}/{document_id}/status",
    summary="Get the status of an uploaded file for a specific chat session",
    status_code=status.HTTP_200_OK,
)
@default_limit
async def get_uploaded_file_status(
    request: Request,
    chat_session_id: UUID,
    document_id: UUID,
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
) -> JSONResponse:
    """
    Retrieve the status of an uploaded file for a specific chat session.
    """
    document_status = await upload_service.get_uploaded_file_status(
        chat_session_id=chat_session_id,
        user_id=request.state.user_id,
        document_id=document_id,
    )

    return send_success_response(
        message="Uploaded file status retrieved successfully.",
        status_code=status.HTTP_200_OK,
        data={"status": document_status},
    )


@upload_router.post(
    path="/{chat_session_id}/{file_id}/reprocess",
    summary="Reprocess an uploaded file for a specific chat session",
    status_code=status.HTTP_202_ACCEPTED,
)
@uploads_limit
async def reprocess(
    request: Request,
    chat_session_id: UUID,
    file_id: UUID,
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    runner: Annotated[IngestionRunner, Depends(get_ingestion_runner)],
):
    document = await upload_service.reprocess_uploaded_file(
        chat_session_id=chat_session_id,
        user_id=request.state.user_id,
        document_id=file_id,
    )
    runner.start(build_job(document))
    return document.viewable()


@upload_router.delete(
    path="/{chat_session_id}/{file_id}",
    summary="Delete an uploaded file from a specific chat session",
    status_code=status.HTTP_200_OK,
)
@default_limit
async def delete_uploaded_file(
    request: Request,
    chat_session_id: UUID,
    file_id: UUID,
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
) -> JSONResponse:
    """
    Delete an uploaded file and its stored content. Deleting a file that no
    longer exists succeeds.
    """
    await upload_service.delete_uploaded_file(
        chat_session_id=chat_session_id,
        user_id=request.state.user_id,
        document_id=file_id,
    )

    return send_success_response(
        message="Uploaded file deleted successfully.",
        status_code=status.HTTP_200_OK,
    )


@upload_router.post(
    path="/{chat_session_id}/batch-delete",
    summary="Delete several uploaded files from a specific chat session",
    status_code=status.HTTP_200_OK,
)
@default_limit
async def delete_uploaded_files(
    request: Request,
    chat_session_id: UUID,
    request_body: DeleteUploadedFilesRequest,
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
) -> JSONResponse:
    """
    Delete several uploaded files at once. Ids that are not in the chat
    session are skipped, and the response says how many were deleted.
    """
    deleted = await upload_service.delete_uploaded_files(
        chat_session_id=chat_session_id,
        user_id=request.state.user_id,
        document_ids=request_body.file_ids,
    )

    return send_success_response(
        message="Uploaded files deleted successfully.",
        status_code=status.HTTP_200_OK,
        data={"deletedCount": deleted},
    )
