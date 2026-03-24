from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.connectors.postgres_connector import PostgresConnector
from app.models.common import SourceType, SyncMode
from app.models.source import Source
from app.repositories.source_repo import InMemorySourceRepository
from app.schemas.source import CreateSourceRequest
from app.services.source_service import SourceService


class StubPostgresConnector(PostgresConnector):
    def __init__(self, *, rows: list[dict], columns: set[str], batch_size: int = 2) -> None:
        super().__init__(batch_size=batch_size)
        self.rows = rows
        self.columns = columns

    def _list_columns(self, resolved) -> set[str]:
        return set(self.columns)

    def _fetch_rows(self, resolved, *, incremental: bool, cursor, limit: int) -> list[dict]:
        rows = list(self.rows)
        if incremental:
            updated_cursor, primary_key_cursor = cursor or (None, None)
            if updated_cursor is not None:
                updated_value = self._deserialize_checkpoint_component(updated_cursor)
                primary_key_value = (
                    self._deserialize_checkpoint_component(primary_key_cursor)
                    if primary_key_cursor is not None
                    else None
                )
                rows = [
                    row
                    for row in rows
                    if row[resolved.updated_at_column] > updated_value
                    or (
                        primary_key_value is not None
                        and row[resolved.updated_at_column] == updated_value
                        and row[resolved.primary_key] > primary_key_value
                    )
                ]
            rows.sort(key=lambda row: (row[resolved.updated_at_column], row[resolved.primary_key]))
        else:
            primary_key_cursor = cursor[1] if cursor else None
            if primary_key_cursor is not None:
                primary_key_value = self._deserialize_checkpoint_component(primary_key_cursor)
                rows = [row for row in rows if row[resolved.primary_key] > primary_key_value]
            rows.sort(key=lambda row: row[resolved.primary_key])
        return rows[:limit]


class FailingValidationConnector:
    def test_connection(self, source: Source) -> bool:
        raise RuntimeError("boom")


class PassingValidationConnector:
    def __init__(self) -> None:
        self.called = False

    def test_connection(self, source: Source) -> bool:
        self.called = True
        return True


def build_postgres_source(config_overrides: dict | None = None) -> Source:
    config = {
        "connection_dsn": "postgresql://demo:secret@localhost:5432/knowledge",
        "schema": "public",
        "table": "knowledge_articles",
        "primary_key": "id",
        "title_column": "title",
        "content_column": "content",
        "doc_type_column": "doc_type",
        "updated_at_column": "updated_at",
        "deleted_flag_column": "is_deleted",
        "acl_columns": {
            "roles": "visible_roles",
            "departments": "visible_departments",
        },
        "metadata_columns": {
            "biz_line": "biz_line",
            "owner": "owner_name",
        },
        "batch_size": 2,
    }
    if config_overrides:
        config.update(config_overrides)
    return Source(
        id="src_pg",
        name="知识库 PG 源",
        type=SourceType.POSTGRES,
        config=config,
        sync_mode=SyncMode.INCREMENTAL,
    )


def test_postgres_connector_normalize_maps_acl_metadata_and_checkpoint() -> None:
    connector = PostgresConnector()
    source = build_postgres_source()
    record = {
        "id": 42,
        "title": "请假制度",
        "content": "请假需提前发起审批。",
        "doc_type": "faq",
        "updated_at": datetime(2026, 3, 24, 10, 30, tzinfo=timezone.utc),
        "is_deleted": False,
        "visible_roles": ["employee", "manager"],
        "visible_departments": "hr, finance",
        "biz_line": "hr",
        "owner_name": "alice",
    }

    payload = connector.normalize(source, record)

    assert payload.external_doc_id == "42"
    assert payload.title == "请假制度"
    assert payload.doc_type == "faq"
    assert payload.deleted is False
    assert payload.metadata["biz_line"] == "hr"
    assert payload.metadata["owner"] == "alice"
    assert payload.metadata["updated_at"] == "2026-03-24T10:30:00Z"
    assert payload.checkpoint_value == "2026-03-24T10:30:00Z|42"
    assert sorted((item.type.value, item.value) for item in payload.acl) == [
        ("department", "finance"),
        ("department", "hr"),
        ("role", "employee"),
        ("role", "manager"),
    ]


def test_postgres_connector_incremental_pull_uses_composite_checkpoint() -> None:
    rows = [
        {"id": 1, "title": "a", "content": "A", "updated_at": 1, "is_deleted": False},
        {"id": 2, "title": "b", "content": "B", "updated_at": 2, "is_deleted": False},
        {"id": 3, "title": "c", "content": "C", "updated_at": 2, "is_deleted": False},
        {"id": 4, "title": "d", "content": "D", "updated_at": 3, "is_deleted": True},
    ]
    connector = StubPostgresConnector(
        rows=rows,
        columns={"id", "title", "content", "updated_at", "is_deleted"},
        batch_size=2,
    )
    source = build_postgres_source(
        {
            "doc_type_column": None,
            "acl_columns": {},
            "metadata_columns": {},
        }
    )

    assert connector.test_connection(source) is True
    pulled_rows = connector.pull_incremental(source, "2|2")

    assert [row["id"] for row in pulled_rows] == [3, 4]


def test_postgres_connector_test_connection_rejects_missing_columns() -> None:
    connector = StubPostgresConnector(rows=[], columns={"id", "title", "updated_at", "is_deleted"})
    source = build_postgres_source()

    with pytest.raises(ValueError, match="missing columns"):
        connector.test_connection(source)


def test_source_service_validates_postgres_source_on_create() -> None:
    repo = InMemorySourceRepository()
    connector = PassingValidationConnector()
    service = SourceService(repo, postgres_connector=connector)

    source = service.create_source(
        CreateSourceRequest(
            name="知识库 PG 源",
            type=SourceType.POSTGRES,
            config=build_postgres_source().config,
            sync_mode=SyncMode.INCREMENTAL,
            enabled=True,
        )
    )

    assert connector.called is True
    assert repo.get(source.id) is not None


def test_source_service_wraps_postgres_validation_error() -> None:
    repo = InMemorySourceRepository()
    service = SourceService(repo, postgres_connector=FailingValidationConnector())

    with pytest.raises(ValueError, match="postgres source validation failed: boom"):
        service.create_source(
            CreateSourceRequest(
                name="知识库 PG 源",
                type=SourceType.POSTGRES,
                config=build_postgres_source().config,
                sync_mode=SyncMode.INCREMENTAL,
                enabled=True,
            )
        )
