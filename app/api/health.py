from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.responses import success_response
from app.core.config import get_settings
from app.core.database import check_database_health
from app.core.minio import check_minio_health
from app.core.redis import check_redis_health

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict:
    settings = get_settings()
    data = {
        "app": {"status": "ok", "env": settings.app_env, "name": settings.app_name},
        "database": check_database_health(settings),
        "redis": check_redis_health(settings),
        "minio": check_minio_health(settings),
        "model": {"status": "development", "detail": "当前使用 HashEmbeddingService 作为开发占位实现"},
    }
    return success_response(request, data)
