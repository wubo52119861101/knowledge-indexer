from __future__ import annotations

import gzip
import json
from io import BytesIO
from typing import Any, Protocol
from urllib.parse import urlparse

from app.core.config import Settings
from app.core.health import build_health_payload, short_error
from app.core.logger import get_logger

try:
    from minio import Minio
except ModuleNotFoundError:
    Minio = None


logger = get_logger(__name__)


class ObjectStorageConfigurationError(RuntimeError):
    pass


class ObjectStorageRepository(Protocol):
    def upload_jsonl_gz(self, object_name: str, records: list[Any]) -> str | None: ...


class DisabledObjectStorageRepository:
    def upload_jsonl_gz(self, object_name: str, records: list[Any]) -> str | None:
        return None


class InMemoryObjectStorageRepository:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload_jsonl_gz(self, object_name: str, records: list[Any]) -> str | None:
        self.objects[object_name] = _encode_jsonl_gz(records)
        return object_name

    def read_jsonl(self, object_name: str) -> list[Any]:
        payload = gzip.decompress(self.objects[object_name]).decode("utf-8")
        lines = [line for line in payload.splitlines() if line.strip()]
        return [json.loads(line) for line in lines]


class MinioObjectStorageRepository:
    def __init__(self, client: Any, *, bucket: str) -> None:
        self._client = client
        self._bucket = bucket
        self._bucket_verified = False

    def upload_jsonl_gz(self, object_name: str, records: list[Any]) -> str | None:
        self._ensure_bucket_available()
        payload = _encode_jsonl_gz(records)
        self._client.put_object(
            self._bucket,
            object_name,
            data=BytesIO(payload),
            length=len(payload),
            content_type="application/gzip",
        )
        return object_name

    def _ensure_bucket_available(self) -> None:
        if self._bucket_verified:
            return
        if not self._client.bucket_exists(self._bucket):
            raise ObjectStorageConfigurationError(f"MinIO bucket 不存在: {self._bucket}")
        self._bucket_verified = True


def build_object_storage_repository(settings: Settings) -> ObjectStorageRepository:
    if not _has_any_minio_configuration(settings):
        return DisabledObjectStorageRepository()
    try:
        client = create_minio_client(settings)
    except Exception as exc:
        logger.warning("failed to build minio repository, archive disabled: %s", exc)
        return DisabledObjectStorageRepository()
    return MinioObjectStorageRepository(client, bucket=settings.minio_bucket or "")


def create_minio_client(settings: Settings) -> Any:
    if not settings.minio_endpoint:
        raise ObjectStorageConfigurationError("MINIO_ENDPOINT 未配置")
    if not settings.minio_access_key:
        raise ObjectStorageConfigurationError("MINIO_ACCESS_KEY 未配置")
    if not settings.minio_secret_key:
        raise ObjectStorageConfigurationError("MINIO_SECRET_KEY 未配置")
    if not settings.minio_bucket:
        raise ObjectStorageConfigurationError("MINIO_BUCKET 未配置")
    if Minio is None:
        raise ObjectStorageConfigurationError("缺少 minio 依赖，请安装 `.[infra]` 后再启用 MinIO 归档")

    endpoint, secure = _normalize_minio_endpoint(settings.minio_endpoint)
    return Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
    )


def check_minio_health(settings: Settings) -> dict[str, Any]:
    if not _has_any_minio_configuration(settings):
        return build_health_payload(
            status="disabled",
            detail="MinIO 归档未启用",
            configuration="disabled",
            connectivity="not_required",
            capability="archive_disabled",
        )

    missing_fields = [
        field_name
        for field_name, field_value in {
            "MINIO_ENDPOINT": settings.minio_endpoint,
            "MINIO_ACCESS_KEY": settings.minio_access_key,
            "MINIO_SECRET_KEY": settings.minio_secret_key,
            "MINIO_BUCKET": settings.minio_bucket,
        }.items()
        if not field_value
    ]
    if missing_fields:
        return build_health_payload(
            status="misconfigured",
            detail=f"MinIO 配置不完整，缺少: {', '.join(missing_fields)}",
            configuration="misconfigured",
            connectivity="unknown",
            capability="archive_unavailable",
        )

    if Minio is None:
        return build_health_payload(
            status="degraded",
            detail="已配置 MinIO，但当前环境未安装 minio 依赖",
            configuration="configured",
            connectivity="unavailable",
            capability="archive_unavailable",
        )

    try:
        client = create_minio_client(settings)
        bucket_exists = bool(client.bucket_exists(settings.minio_bucket or ""))
    except Exception as exc:
        return build_health_payload(
            status="configured",
            detail=f"MinIO 已配置，但连通性检查失败: {short_error(exc)}",
            configuration="configured",
            connectivity="unreachable",
            capability="archive_unavailable",
        )

    if not bucket_exists:
        return build_health_payload(
            status="configured",
            detail=f"MinIO 服务可达，但 bucket 不存在: {settings.minio_bucket}",
            configuration="configured",
            connectivity="reachable",
            capability="bucket_missing",
        )

    return build_health_payload(
        status="reachable",
        detail=f"MinIO 服务可达，bucket `{settings.minio_bucket}` 可用",
        configuration="configured",
        connectivity="reachable",
        capability="archive_ready",
    )


def _has_any_minio_configuration(settings: Settings) -> bool:
    return any(
        [
            settings.minio_endpoint,
            settings.minio_access_key,
            settings.minio_secret_key,
            settings.minio_bucket,
        ]
    )


def _normalize_minio_endpoint(endpoint: str) -> tuple[str, bool]:
    raw_endpoint = endpoint.strip()
    parsed = urlparse(raw_endpoint if "://" in raw_endpoint else f"http://{raw_endpoint}")
    host = parsed.netloc or parsed.path
    if not host:
        raise ObjectStorageConfigurationError("MINIO_ENDPOINT 非法")
    return host, parsed.scheme == "https"


def _encode_jsonl_gz(records: list[Any]) -> bytes:
    payload = "".join(f"{json.dumps(record, ensure_ascii=False, default=str)}\n" for record in records)
    return gzip.compress(payload.encode("utf-8"))
