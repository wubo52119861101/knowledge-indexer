from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.responses import success_response
from app.core.container import ServiceContainer, get_container
from app.core.database import check_database_health
from app.core.minio import check_minio_health
from app.core.redis import check_redis_health

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> dict:
    settings = container.settings
    data = {
        "app": {"status": "ok", "env": settings.app_env, "name": settings.app_name},
        "database": check_database_health(settings),
        "redis": check_redis_health(settings),
        "minio": check_minio_health(settings),
        "pipeline_engine": container.pipeline_engine_service.resolve_for_health().model_dump(mode="json"),
    }
    return success_response(request, data)
