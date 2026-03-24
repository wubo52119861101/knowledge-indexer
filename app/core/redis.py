from __future__ import annotations

from typing import Any

from app.core.config import Settings

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


def check_redis_health(settings: Settings) -> dict[str, str]:
    if not settings.redis_url:
        return {"status": "disabled", "detail": "REDIS_URL 未配置"}
    if redis_lib is None:
        return {"status": "degraded", "detail": "已配置 Redis 地址，但当前环境未安装 redis 依赖"}
    return {"status": "configured", "detail": "Redis 地址已配置，可用于异步同步队列"}
