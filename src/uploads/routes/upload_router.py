from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, status, Request, UploadFile, File, BackgroundTasks
from fastapi.params import Depends
from starlette.responses import JSONResponse

from src.response.delivery import send_success_response
from src.uploads.dependencies import get_upload_service
from src.uploads.services.ingestion_service import IngestionService
from src.uploads.services.upload_service import UploadService

upload_router = APIRouter(prefix="/uploads", tags=["Uploads"])


@upload_router.post(
    path="{chat_session_id}",
    summary="Upload a file to a specific chat session",
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_file(
    request: Request,
    chat_session_id: UUID,
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    background_tasks: BackgroundTasks,
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

    job = IngestionService.build_job(document=document)

    background_tasks.add_task(IngestionService.run_ingestion, job, request)

    return send_success_response(
        message="File uploaded successfully.",
        status_code=status.HTTP_202_ACCEPTED,
        data=document.viewable(),
    )


async def get_uploaded_files():
    pass


async def get_uploaded_file_status():
    pass
