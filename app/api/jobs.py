from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.responses import success_response
from app.core.container import ServiceContainer, get_container
from app.core.security import verify_internal_token
from app.schemas.job import JobItem

router = APIRouter(prefix="/internal/jobs", tags=["jobs"], dependencies=[Depends(verify_internal_token)])


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> dict:
    job = container.job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return success_response(request, JobItem.model_validate(job, from_attributes=True).model_dump(mode="json"))
