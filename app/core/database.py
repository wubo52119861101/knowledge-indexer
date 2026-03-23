from __future__ import annotations

from app.core.config import Settings


def check_database_health(settings: Settings) -> dict[str, str]:
    if not settings.database_url:
        return {"status": "disabled", "detail": "DATABASE_URL 未配置"}
    return {"status": "configured", "detail": "已配置 PostgreSQL 连接串，待接入正式持久化仓储"}
