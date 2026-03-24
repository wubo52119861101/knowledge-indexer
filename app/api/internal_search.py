from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.responses import success_response
from app.core.container import ServiceContainer, get_container
from app.core.security import verify_internal_token
from app.schemas.retrieval import SearchRequest

router = APIRouter(prefix="/internal", tags=["retrieval"], dependencies=[Depends(verify_internal_token)])


@router.post("/search")
async def internal_search(
    payload: SearchRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> dict:
    result = container.qa_service.search(
        query=payload.query,
        top_k=payload.top_k,
        filters=payload.filters,
        acl_context=payload.acl_context,
    )
    return success_response(request, result.model_dump(mode="json"))
