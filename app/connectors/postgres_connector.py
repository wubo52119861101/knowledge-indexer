from __future__ import annotations

import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterator
from urllib.parse import urlparse

from app.connectors.base import BaseConnector
from app.core.database import postgres_connection, row_to_dict
from app.models.common import SourceType, SyncMode
from app.models.source import Source
from app.schemas.document import AclEntryPayload, DocumentPayload

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_DSN_SCHEMES = {"postgres", "postgresql"}
_UNSAFE_WHERE_TOKENS = (";", "--", "/*", "*/")
_ALLOWED_WHERE_RE = re.compile(r"^[A-Za-z0-9_\s\.=<>!(),'\"%-]+$")
_ACL_TYPE_MAPPING = {
    "user": "user",
    "users": "user",
    "role": "role",
    "roles": "role",
    "department": "department",
    "departments": "department",
    "tag": "tag",
    "tags": "tag",
}


@dataclass(slots=True)
class ResolvedPostgresSourceConfig:
    connection_dsn: str
    schema: str
    table: str
    primary_key: str
    title_column: str | None
    content_column: str
    doc_type_column: str | None
    updated_at_column: str | None
    deleted_flag_column: str | None
    acl_columns: dict[str, str]
    metadata_columns: dict[str, str]
    where_clause: str | None
    batch_size: int

    def required_columns(self) -> set[str]:
        columns = {self.primary_key, self.content_column}
        if self.title_column:
            columns.add(self.title_column)
        if self.doc_type_column:
            columns.add(self.doc_type_column)
        if self.updated_at_column:
            columns.add(self.updated_at_column)
        if self.deleted_flag_column:
            columns.add(self.deleted_flag_column)
        columns.update(self.acl_columns.values())
        columns.update(self.metadata_columns.values())
        return columns

    def selected_columns(self) -> list[str]:
        ordered = [
            self.primary_key,
            self.title_column,
            self.content_column,
            self.doc_type_column,
            self.updated_at_column,
            self.deleted_flag_column,
            *self.acl_columns.values(),
            *self.metadata_columns.values(),
        ]
        seen: set[str] = set()
        result: list[str] = []
        for column in ordered:
            if not column or column in seen:
                continue
            seen.add(column)
            result.append(column)
        return result


class PostgresConnector(BaseConnector):
    def __init__(
        self,
        *,
        batch_size: int = 500,
        connection_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.default_batch_size = batch_size
        self.connection_factory = connection_factory

    def test_connection(self, source: Source) -> bool:
        resolved = self._resolve_source_config(source, require_incremental_cursor=source.sync_mode is SyncMode.INCREMENTAL)
        self._validate_table_columns(resolved)
        self._fetch_rows(resolved, incremental=False, cursor=None, limit=1)
        return True

    def pull_full(self, source: Source) -> list[Any]:
        resolved = self._resolve_source_config(source)
        self._validate_table_columns(resolved)

        rows: list[dict[str, Any]] = []
        last_primary_key: str | None = None
        while True:
            batch = self._fetch_rows(
                resolved,
                incremental=False,
                cursor=(None, last_primary_key) if last_primary_key is not None else None,
                limit=resolved.batch_size,
            )
            if not batch:
                break
            rows.extend(batch)
            last_primary_key = self._normalize_checkpoint_component(batch[-1][resolved.primary_key])
            if len(batch) < resolved.batch_size:
                break
        return rows

    def pull_incremental(self, source: Source, checkpoint: str | None) -> list[Any]:
        resolved = self._resolve_source_config(source, require_incremental_cursor=True)
        self._validate_table_columns(resolved)

        updated_cursor, primary_key_cursor = self._split_checkpoint(checkpoint)
        rows: list[dict[str, Any]] = []
        while True:
            batch = self._fetch_rows(
                resolved,
                incremental=True,
                cursor=(updated_cursor, primary_key_cursor),
                limit=resolved.batch_size,
            )
            if not batch:
                break
            rows.extend(batch)
            updated_cursor = self._normalize_checkpoint_component(batch[-1][resolved.updated_at_column])
            primary_key_cursor = self._normalize_checkpoint_component(batch[-1][resolved.primary_key])
            if len(batch) < resolved.batch_size:
                break
        return rows

    def normalize(self, source: Source, record: Any) -> DocumentPayload:
        resolved = self._resolve_source_config(source)
        if not isinstance(record, dict):
            raise ValueError("postgres source record must be a dict-like row")

        external_doc_id = self._require_value(record, resolved.primary_key, "primary_key")
        deleted = self._to_bool(record.get(resolved.deleted_flag_column)) if resolved.deleted_flag_column else False
        title = str(record.get(resolved.title_column) or external_doc_id) if resolved.title_column else external_doc_id
        content_raw = record.get(resolved.content_column)
        if not deleted and (content_raw is None or not str(content_raw).strip()):
            raise ValueError(f"content column '{resolved.content_column}' is empty for record {external_doc_id}")
        content = str(content_raw) if content_raw not in (None, "") else f"[deleted] {external_doc_id}"
        doc_type = str(record.get(resolved.doc_type_column) or "text") if resolved.doc_type_column else "text"

        metadata = {
            key: self._to_json_safe_value(record.get(column_name))
            for key, column_name in resolved.metadata_columns.items()
        }
        updated_at_value = record.get(resolved.updated_at_column) if resolved.updated_at_column else None
        if resolved.updated_at_column:
            metadata.setdefault("updated_at", self._to_json_safe_value(updated_at_value))
        metadata.setdefault("primary_key", external_doc_id)
        if resolved.deleted_flag_column:
            metadata.setdefault("deleted", deleted)

        acl_entries: list[AclEntryPayload] = []
        for mapping_key, column_name in resolved.acl_columns.items():
            acl_type = _ACL_TYPE_MAPPING[mapping_key]
            for acl_value in self._to_list(record.get(column_name)):
                acl_entries.append(AclEntryPayload(type=acl_type, value=acl_value))

        checkpoint_value = None
        if resolved.updated_at_column and updated_at_value is not None:
            checkpoint_value = self._build_checkpoint(updated_at_value, external_doc_id)

        return DocumentPayload(
            external_doc_id=external_doc_id,
            title=title,
            content=content,
            doc_type=doc_type,
            metadata=metadata,
            acl=acl_entries,
            deleted=deleted,
            checkpoint_value=checkpoint_value,
        )

    def _resolve_source_config(
        self,
        source: Source,
        *,
        require_incremental_cursor: bool = False,
    ) -> ResolvedPostgresSourceConfig:
        if source.type is not SourceType.POSTGRES:
            raise ValueError(f"unsupported source type for PostgresConnector: {source.type}")

        config = dict(source.config or {})
        connection_dsn = self._require_non_empty_string(
            config.get("connection_dsn") or config.get("connection_string"),
            "connection_dsn",
        )
        self._validate_connection_dsn(connection_dsn)

        schema = self._normalize_identifier(config.get("schema") or "public", field_name="schema")
        table = self._normalize_identifier(config.get("table") or config.get("table_name"), field_name="table")
        primary_key = self._normalize_identifier(config.get("primary_key"), field_name="primary_key")
        content_column = self._normalize_identifier(config.get("content_column"), field_name="content_column")
        title_column = self._normalize_optional_identifier(config.get("title_column"), field_name="title_column")
        doc_type_column = self._normalize_optional_identifier(config.get("doc_type_column"), field_name="doc_type_column")
        updated_at_column = self._normalize_optional_identifier(config.get("updated_at_column"), field_name="updated_at_column")
        deleted_flag_column = self._normalize_optional_identifier(
            config.get("deleted_flag_column"),
            field_name="deleted_flag_column",
        )
        metadata_columns = self._normalize_metadata_columns(config.get("metadata_columns") or {})
        acl_columns = self._normalize_acl_columns(config.get("acl_columns") or {})
        where_clause = self._normalize_where_clause(config.get("where_clause"))
        batch_size = self._normalize_batch_size(config.get("batch_size"))

        if require_incremental_cursor and not updated_at_column:
            raise ValueError("postgres incremental sync requires config.updated_at_column")

        return ResolvedPostgresSourceConfig(
            connection_dsn=connection_dsn,
            schema=schema,
            table=table,
            primary_key=primary_key,
            title_column=title_column,
            content_column=content_column,
            doc_type_column=doc_type_column,
            updated_at_column=updated_at_column,
            deleted_flag_column=deleted_flag_column,
            acl_columns=acl_columns,
            metadata_columns=metadata_columns,
            where_clause=where_clause,
            batch_size=batch_size,
        )

    def _normalize_metadata_columns(self, value: Any) -> dict[str, str]:
        if isinstance(value, list):
            result = {}
            for item in value:
                column_name = self._normalize_identifier(item, field_name="metadata_columns")
                result[column_name] = column_name
            return result
        if not isinstance(value, dict):
            raise ValueError("config.metadata_columns must be a dict or list")
        result: dict[str, str] = {}
        for metadata_key, column_name in value.items():
            key = str(metadata_key).strip()
            if not key:
                raise ValueError("config.metadata_columns contains empty metadata key")
            result[key] = self._normalize_identifier(column_name, field_name=f"metadata_columns.{key}")
        return result

    def _normalize_acl_columns(self, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ValueError("config.acl_columns must be a dict")
        result: dict[str, str] = {}
        for acl_key, column_name in value.items():
            normalized_key = str(acl_key).strip().lower()
            if normalized_key not in _ACL_TYPE_MAPPING:
                allowed = ", ".join(sorted(_ACL_TYPE_MAPPING))
                raise ValueError(f"unsupported acl_columns key '{acl_key}', allowed: {allowed}")
            result[normalized_key] = self._normalize_identifier(column_name, field_name=f"acl_columns.{normalized_key}")
        return result

    def _normalize_where_clause(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        clause = str(value).strip()
        if not clause:
            return None
        lowered = clause.lower()
        if any(token in clause for token in _UNSAFE_WHERE_TOKENS):
            raise ValueError("config.where_clause contains unsafe SQL token")
        if any(keyword in f" {lowered} " for keyword in (" insert ", " update ", " delete ", " drop ", " alter ", " create ")):
            raise ValueError("config.where_clause contains unsupported SQL keyword")
        if not _ALLOWED_WHERE_RE.fullmatch(clause):
            raise ValueError("config.where_clause contains unsupported characters")
        return clause

    def _normalize_batch_size(self, value: Any) -> int:
        batch_size = self.default_batch_size if value in (None, "") else int(value)
        if batch_size <= 0 or batch_size > 5000:
            raise ValueError("config.batch_size must be between 1 and 5000")
        return batch_size

    def _validate_connection_dsn(self, connection_dsn: str) -> None:
        parsed = urlparse(connection_dsn)
        if parsed.scheme.lower() not in _ALLOWED_DSN_SCHEMES:
            raise ValueError("config.connection_dsn must start with postgres:// or postgresql://")
        if not parsed.hostname:
            raise ValueError("config.connection_dsn must include hostname")
        if not parsed.path or parsed.path == "/":
            raise ValueError("config.connection_dsn must include database name")

    def _validate_table_columns(self, resolved: ResolvedPostgresSourceConfig) -> None:
        available_columns = self._list_columns(resolved)
        if not available_columns:
            raise ValueError(f"table {resolved.schema}.{resolved.table} does not exist or has no readable columns")
        missing_columns = sorted(resolved.required_columns() - available_columns)
        if missing_columns:
            missing_display = ", ".join(missing_columns)
            raise ValueError(f"table {resolved.schema}.{resolved.table} is missing columns: {missing_display}")

    def _list_columns(self, resolved: ResolvedPostgresSourceConfig) -> set[str]:
        with self._connection(resolved.connection_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position ASC
                    """,
                    (resolved.schema, resolved.table),
                )
                rows = cursor.fetchall()
                return {str(row[0]) for row in rows}

    def _fetch_rows(
        self,
        resolved: ResolvedPostgresSourceConfig,
        *,
        incremental: bool,
        cursor: tuple[str | None, str | None] | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        select_columns = ", ".join(self._quote_identifier(column) for column in resolved.selected_columns())
        conditions: list[str] = []
        params: list[Any] = []
        if resolved.where_clause:
            conditions.append(f"({resolved.where_clause})")

        primary_key_sql = self._quote_identifier(resolved.primary_key)
        if incremental:
            if resolved.updated_at_column is None:
                raise ValueError("postgres incremental sync requires config.updated_at_column")
            updated_at_sql = self._quote_identifier(resolved.updated_at_column)
            if cursor and cursor[0] is not None:
                updated_value = self._deserialize_checkpoint_component(cursor[0])
                if cursor[1] is None:
                    conditions.append(f"{updated_at_sql} > %s")
                    params.append(updated_value)
                else:
                    primary_key_value = self._deserialize_checkpoint_component(cursor[1])
                    conditions.append(
                        f"({updated_at_sql} > %s OR ({updated_at_sql} = %s AND {primary_key_sql} > %s))"
                    )
                    params.extend([updated_value, updated_value, primary_key_value])
            order_by = f" ORDER BY {updated_at_sql} ASC, {primary_key_sql} ASC"
        else:
            if cursor and cursor[1] is not None:
                conditions.append(f"{primary_key_sql} > %s")
                params.append(self._deserialize_checkpoint_component(cursor[1]))
            order_by = f" ORDER BY {primary_key_sql} ASC"

        where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = (
            f"SELECT {select_columns} "
            f"FROM {self._qualified_table(resolved.schema, resolved.table)}"
            f"{where_sql}{order_by} LIMIT %s"
        )
        params.append(limit)

        with self._connection(resolved.connection_dsn) as connection:
            with connection.cursor() as cursor_obj:
                cursor_obj.execute(query, tuple(params))
                rows = cursor_obj.fetchall()
                return [
                    row_payload
                    for row in rows
                    if (row_payload := row_to_dict(cursor_obj.description, row)) is not None
                ]

    @contextmanager
    def _connection(self, connection_dsn: str) -> Iterator[Any]:
        if self.connection_factory is not None:
            with self.connection_factory(connection_dsn) as connection:
                yield connection
            return
        with postgres_connection(connection_dsn) as connection:
            yield connection

    def _require_non_empty_string(self, value: Any, field_name: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"postgres source requires config.{field_name}")
        return normalized

    def _normalize_identifier(self, value: Any, *, field_name: str) -> str:
        normalized = self._require_non_empty_string(value, field_name)
        if not _IDENTIFIER_RE.fullmatch(normalized):
            raise ValueError(f"config.{field_name} contains invalid identifier '{normalized}'")
        return normalized

    def _normalize_optional_identifier(self, value: Any, *, field_name: str) -> str | None:
        if value in (None, ""):
            return None
        return self._normalize_identifier(value, field_name=field_name)

    def _qualified_table(self, schema: str, table: str) -> str:
        return f'{self._quote_identifier(schema)}.{self._quote_identifier(table)}'

    def _quote_identifier(self, identifier: str) -> str:
        if not _IDENTIFIER_RE.fullmatch(identifier):
            raise ValueError(f"invalid SQL identifier '{identifier}'")
        return f'"{identifier}"'

    def _require_value(self, row: dict[str, Any], column_name: str, label: str) -> str:
        value = row.get(column_name)
        if value in (None, ""):
            raise ValueError(f"postgres source {label} column '{column_name}' is empty")
        return str(value)

    def _build_checkpoint(self, updated_at_value: Any, primary_key_value: Any) -> str:
        return f"{self._normalize_checkpoint_component(updated_at_value)}|{self._normalize_checkpoint_component(primary_key_value)}"

    def _split_checkpoint(self, checkpoint: str | None) -> tuple[str | None, str | None]:
        if not checkpoint:
            return None, None
        if "|" not in checkpoint:
            return checkpoint, None
        updated_at_cursor, primary_key_cursor = checkpoint.split("|", 1)
        return updated_at_cursor or None, primary_key_cursor or None

    def _normalize_checkpoint_component(self, value: Any) -> str:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            else:
                value = value.astimezone(timezone.utc)
            return value.isoformat().replace("+00:00", "Z")
        return str(value)

    def _deserialize_checkpoint_component(self, value: str) -> Any:
        normalized = value.strip()
        if not normalized:
            return normalized
        if re.fullmatch(r"-?\d+", normalized):
            try:
                return int(normalized)
            except ValueError:
                return normalized
        if re.fullmatch(r"-?\d+\.\d+", normalized):
            try:
                return float(normalized)
            except ValueError:
                return normalized
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            return normalized

    def _to_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}
        return bool(value)

    def _to_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("[") and stripped.endswith("]"):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except json.JSONDecodeError:
                    pass
            if "," in stripped:
                return [item.strip() for item in stripped.split(",") if item.strip()]
            return [stripped]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    def _to_json_safe_value(self, value: Any) -> Any:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            else:
                value = value.astimezone(timezone.utc)
            return value.isoformat().replace("+00:00", "Z")
        if isinstance(value, dict):
            return {str(key): self._to_json_safe_value(nested) for key, nested in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._to_json_safe_value(item) for item in value]
        return value
