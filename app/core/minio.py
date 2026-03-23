from __future__ import annotations

from app.core.config import Settings


def check_minio_health(settings: Settings) -> dict[str, str]:
    if not settings.minio_endpoint:
        return {"status": "disabled", "detail": "MINIO_ENDPOINT 未配置"}
    return {"status": "configured", "detail": f"已配置 MinIO 端点 {settings.minio_endpoint}"}
