from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.responses import success_response
from app.core.container import ServiceContainer, get_container
from app.core.database import mask_sensitive_data
from app.core.security import verify_internal_token
from app.schemas.source import CreateSourceRequest, SourceDetail, SourceItem, TriggerSyncRequest, TriggerSyncResponse
from app.schemas.job import JobItem

router = APIRouter(prefix="/internal/sources", tags=["sources"], dependencies=[Depends(verify_internal_token)])


@router.post("")
async def create_source(
    payload: CreateSourceRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> dict:
    try:
        source = container.source_service.create_source(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    data = _serialize_source_item(source)
    return success_response(request, data.model_dump(mode="json"))


@router.get("/{source_id}")
async def get_source(
    source_id: str,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> dict:
    source = container.source_service.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")

    latest_job = container.job_service.latest_for_source(source_id)
    detail = SourceDetail(
        source=_serialize_source_item(source),
        latest_job=JobItem.model_validate(latest_job, from_attributes=True) if latest_job else None,
    )
    return success_response(request, detail.model_dump(mode="json"))


@router.post("/{source_id}/sync")
async def trigger_sync(
    source_id: str,
    payload: TriggerSyncRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> dict:
    try:
        job = container.trigger_sync(source_id=source_id, mode=payload.mode, operator=payload.operator)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    response = TriggerSyncResponse(job_id=job.id, status=job.status.value, queued_at=job.created_at)
    return success_response(request, response.model_dump(mode="json"))


def _serialize_source_item(source) -> SourceItem:
    return SourceItem(
        id=source.id,
        name=source.name,
        type=source.type,
        config=mask_sensitive_data(source.config),
        sync_mode=source.sync_mode,
        enabled=source.enabled,
        last_sync_at=source.last_sync_at,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )
