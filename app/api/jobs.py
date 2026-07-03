from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session, get_job_dispatcher
from app.core.config import Settings, get_settings
from app.models.job import JobStatus
from app.repositories.jobs import JobRepository
from app.schemas.jobs import (
    JobListResponse,
    JobResultsResponse,
    JobStatusResponse,
    JobUploadResponse,
)
from app.services.dispatcher import JobDispatcher, JobDispatchError
from app.services.jobs import (
    CsvValidationError,
    JobNotFoundError,
    JobResultsUnavailableError,
    JobUploadService,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])

UploadedCsv = Annotated[UploadFile, File()]
DatabaseSession = Annotated[Session, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
DispatcherDependency = Annotated[JobDispatcher, Depends(get_job_dispatcher)]
StatusFilter = Annotated[JobStatus | None, Query(alias="status")]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.post(
    "/upload",
    response_model=JobUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_job(
    file: UploadedCsv,
    session: DatabaseSession,
    settings: SettingsDependency,
    dispatcher: DispatcherDependency,
) -> JobUploadResponse:
    repository = JobRepository(session)
    service = JobUploadService(
        repository=repository,
        dispatcher=dispatcher,
        upload_dir=settings.upload_dir,
    )

    try:
        job = await service.create_from_upload(file)
    except CsvValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except JobDispatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return JobUploadResponse(job_id=job.id, status=job.status)


@router.get("", response_model=JobListResponse)
def list_jobs(
    session: DatabaseSession,
    status_filter: StatusFilter = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> JobListResponse:
    repository = JobRepository(session)
    jobs = repository.list(status=status_filter, limit=limit, offset=offset)
    total = repository.count(status=status_filter)
    return JobListResponse(items=jobs, total=total, limit=limit, offset=offset)


@router.get("/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(
    job_id: UUID,
    session: DatabaseSession,
) -> JobStatusResponse:
    repository = JobRepository(session)
    job = repository.get_with_summary(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    return JobStatusResponse.from_job(job)


@router.get("/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(
    job_id: UUID,
    session: DatabaseSession,
    settings: SettingsDependency,
) -> JobResultsResponse:
    repository = JobRepository(session)
    service = JobUploadService(
        repository=repository,
        dispatcher=None,
        upload_dir=settings.upload_dir,
    )

    try:
        return service.get_results(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except JobResultsUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
