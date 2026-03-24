from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.responses import success_response
from app.core.config import get_settings
from app.core.database import check_database_health
from app.core.health import build_health_payload
from app.core.minio import check_minio_health
from app.core.redis import check_redis_health
from app.services.embedding_service import check_embedding_health

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict:
    settings = get_settings()
    data = {
        "app": {
            "status": "ok",
            "env": settings.app_env,
            "name": settings.app_name,
        },
        "database": check_database_health(settings),
        "redis": check_redis_health(settings),
        "minio": check_minio_health(settings),
        "embedding": check_embedding_health(settings),
        "pipeline_engine": _pipeline_engine_health(),
    }
    return success_response(request, data)



def _pipeline_engine_health() -> dict[str, Any]:
    return build_health_payload(
        status="builtin",
        detail="当前使用内置 IndexingService 作为同步执行引擎",
        configuration="builtin",
        connectivity="not_required",
        capability="indexing_ready",
        extra={"engine": "builtin"},
    )
