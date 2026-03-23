from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.responses import success_response
from app.core.container import ServiceContainer, get_container
from app.core.security import verify_internal_token
from app.schemas.retrieval import AskRequest

router = APIRouter(prefix="/internal", tags=["qa"], dependencies=[Depends(verify_internal_token)])


@router.post("/ask")
async def internal_ask(
    payload: AskRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> dict:
    answer = container.qa_service.ask(
        question=payload.question,
        top_k=payload.top_k,
        filters=payload.filters,
        acl_context=payload.acl_context,
    )
    return success_response(request, answer.model_dump(mode="json"))
