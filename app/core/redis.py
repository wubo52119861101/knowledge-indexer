from __future__ import annotations

from app.core.config import Settings


def check_redis_health(settings: Settings) -> dict[str, str]:
    if not settings.redis_url:
        return {"status": "disabled", "detail": "REDIS_URL 未配置"}
    return {"status": "configured", "detail": "已配置 Redis 地址，当前骨架未启用后台队列"}
