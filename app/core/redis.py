from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.core.health import build_health_payload, short_error

try:
    import redis as redis_lib
except ModuleNotFoundError:
    redis_lib = None


class RedisConfigurationError(RuntimeError):
    pass


class RedisDriverUnavailableError(RuntimeError):
    pass



def create_redis_client(settings: Settings) -> Any:
    if not settings.redis_url:
        raise RedisConfigurationError("REDIS_URL 未配置，无法启用 Redis 队列")
    if redis_lib is None:
        raise RedisDriverUnavailableError("缺少 redis 依赖，请安装 `.[infra]` 后再启用 Redis 队列")
    return redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)



def check_redis_health(settings: Settings) -> dict[str, Any]:
    if not settings.redis_url:
        return build_health_payload(
            status="disabled",
            detail="REDIS_URL 未配置",
            configuration="disabled",
            connectivity="not_required",
            capability="queue_inmemory",
        )
    if redis_lib is None:
        return build_health_payload(
            status="degraded",
            detail="已配置 Redis 地址，但当前环境未安装 redis 依赖",
            configuration="configured",
            connectivity="unavailable",
            capability="queue_unavailable",
        )

    try:
        client = create_redis_client(settings)
        client.ping()
    except Exception as exc:
        return build_health_payload(
            status="configured",
            detail=f"Redis 已配置，但连通性检查失败: {short_error(exc)}",
            configuration="configured",
            connectivity="unreachable",
            capability="queue_unavailable",
        )

    return build_health_payload(
        status="reachable",
        detail="Redis 已连接，可用于异步队列与互斥锁",
        configuration="configured",
        connectivity="reachable",
        capability="queue_ready",
    )
