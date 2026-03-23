from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator, Protocol, Sequence

from app.core.config import Settings

try:
    import psycopg
except ModuleNotFoundError:
    psycopg = None


SENSITIVE_KEY_MARKERS = (
    "password",
    "secret",
    "token",
    "access_key",
    "secret_key",
    "api_key",
    "dsn",
    "database_url",
    "connection_string",
    "connection_dsn",
)
MASKED_VALUE = "******"


class DatabaseConfigurationError(RuntimeError):
    pass


class DatabaseDriverUnavailableError(RuntimeError):
    pass


class CursorLike(Protocol):
    description: Sequence[Any] | None

    def execute(self, query: str, params: Sequence[Any] | None = None) -> Any: ...

    def fetchone(self) -> Sequence[Any] | None: ...

    def fetchall(self) -> list[Sequence[Any]]: ...

    def __enter__(self) -> "CursorLike": ...

    def __exit__(self, exc_type, exc, tb) -> None: ...


class ConnectionLike(Protocol):
    def cursor(self) -> CursorLike: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...

    def __enter__(self) -> "ConnectionLike": ...

    def __exit__(self, exc_type, exc, tb) -> None: ...


ConnectionFactory = Callable[[], Any]


class PostgresRepositoryBase:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self.connection_factory = connection_factory

    def _fetchone(self, query: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                return row_to_dict(cursor.description, row)

    def _fetchall(self, query: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [row_to_dict(cursor.description, row) for row in rows]

    def _execute(self, query: str, params: Sequence[Any] = ()) -> None:
        with self.connection_factory() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _fetchone_write(self, query: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        with self.connection_factory() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    row = cursor.fetchone()
                    payload = row_to_dict(cursor.description, row)
                connection.commit()
                return payload
            except Exception:
                connection.rollback()
                raise


@contextmanager
def postgres_connection(database_url: str | None) -> Iterator[ConnectionLike]:
    if not database_url:
        raise DatabaseConfigurationError("DATABASE_URL 未配置，无法启用 postgres 仓储")
    if psycopg is None:
        raise DatabaseDriverUnavailableError("缺少 psycopg 依赖，请安装 `.[infra]` 后再启用 postgres 仓储")

    connection = psycopg.connect(database_url)
    try:
        yield connection
    finally:
        connection.close()


def create_postgres_connection_factory(settings: Settings) -> ConnectionFactory:
    return lambda: postgres_connection(settings.database_url)


def check_database_health(settings: Settings) -> dict[str, str]:
    backend = settings.repository_backend.lower()
    if backend != "postgres":
        return {"status": "disabled", "detail": f"当前仓储后端为 {backend}，未启用 PostgreSQL 持久化"}
    if not settings.database_url:
        return {"status": "misconfigured", "detail": "REPOSITORY_BACKEND=postgres 但 DATABASE_URL 未配置"}
    if psycopg is None:
        return {"status": "degraded", "detail": "已启用 postgres 仓储，但当前环境未安装 psycopg 依赖"}
    return {"status": "configured", "detail": "PostgreSQL 连接串已配置，仓储可切换为正式持久化实现"}


def row_to_dict(description: Sequence[Any] | None, row: Sequence[Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    if not description:
        return {str(index): value for index, value in enumerate(row)}
    columns = [column[0] if isinstance(column, Sequence) else getattr(column, "name", str(index)) for index, column in enumerate(description)]
    return {column: value for column, value in zip(columns, row, strict=False)}


def mask_sensitive_data(value: Any) -> Any:
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, nested_value in value.items():
            key_lower = key.lower()
            if any(marker in key_lower for marker in SENSITIVE_KEY_MARKERS):
                masked[key] = MASKED_VALUE if nested_value not in (None, "") else nested_value
            else:
                masked[key] = mask_sensitive_data(nested_value)
        return masked
    if isinstance(value, list):
        return [mask_sensitive_data(item) for item in value]
    return value


def to_pgvector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(item, ".12g") for item in vector) + "]"


def from_pgvector(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, tuple):
        return [float(item) for item in value]
    if isinstance(value, memoryview):
        value = value.tobytes().decode("utf-8")
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        stripped = value.strip().lstrip("[").rstrip("]")
        if not stripped:
            return []
        return [float(item.strip()) for item in stripped.split(",")]
    raise TypeError(f"unsupported pgvector payload type: {type(value)!r}")
