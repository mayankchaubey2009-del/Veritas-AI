from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from app.models.entities import UserRole
from app.schemas.auth import AuthenticatedUser
from app.schemas.job import BackgroundJobEnqueueRequest, BackgroundJobResponse
from app.services.auth_service import (
    AuthService,
    require_authenticated_user,
    require_roles,
)
from app.services.job_service import JobService

router = APIRouter(tags=["Phase 6 — Background Processing & Job Recovery"])


@router.get("/jobs", response_model=List[BackgroundJobResponse])
def list_background_jobs(
    investigation_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> List[BackgroundJobResponse]:
    if investigation_id:
        AuthService.check_investigation_access(
            investigation_id, current_user, require_write=False
        )
    return JobService.list_jobs(investigation_id=investigation_id, limit=limit)


@router.get(
    "/investigations/{investigation_id}/jobs",
    response_model=List[BackgroundJobResponse],
)
def list_investigation_jobs(
    investigation_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> List[BackgroundJobResponse]:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=False
    )
    return JobService.list_jobs(investigation_id=investigation_id, limit=limit)


@router.post(
    "/jobs/enqueue",
    response_model=BackgroundJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def enqueue_background_job(
    payload: BackgroundJobEnqueueRequest,
    current_user: AuthenticatedUser = Depends(
        require_roles(
            UserRole.ADMIN.value,
            UserRole.INVESTIGATOR.value,
            UserRole.REVIEWER.value,
        )
    ),
) -> BackgroundJobResponse:
    AuthService.check_investigation_access(
        payload.investigation_id, current_user, require_write=True
    )
    return JobService.enqueue_job(payload=payload, current_user=current_user)


@router.get("/jobs/{job_id}", response_model=BackgroundJobResponse)
def get_background_job(
    job_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> BackgroundJobResponse:
    job = JobService.get_job(job_id)
    AuthService.check_investigation_access(
        job.investigation_id, current_user, require_write=False
    )
    return job


@router.post("/jobs/{job_id}/retry", response_model=BackgroundJobResponse)
def retry_background_job(
    job_id: str,
    current_user: AuthenticatedUser = Depends(
        require_roles(
            UserRole.ADMIN.value,
            UserRole.INVESTIGATOR.value,
            UserRole.REVIEWER.value,
        )
    ),
) -> BackgroundJobResponse:
    job = JobService.get_job(job_id)
    AuthService.check_investigation_access(
        job.investigation_id, current_user, require_write=True
    )
    return JobService.retry_job(job_id=job_id, current_user=current_user)


@router.post("/jobs/{job_id}/cancel", response_model=BackgroundJobResponse)
def cancel_background_job(
    job_id: str,
    current_user: AuthenticatedUser = Depends(
        require_roles(
            UserRole.ADMIN.value,
            UserRole.INVESTIGATOR.value,
            UserRole.REVIEWER.value,
        )
    ),
) -> BackgroundJobResponse:
    job = JobService.get_job(job_id)
    AuthService.check_investigation_access(
        job.investigation_id, current_user, require_write=True
    )
    return JobService.cancel_job(job_id=job_id, current_user=current_user)
