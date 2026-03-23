from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector
from app.models.source import Source
from app.schemas.document import DocumentPayload


class PostgresConnector(BaseConnector):
    def test_connection(self, source: Source) -> bool:
        raise NotImplementedError("PostgresConnector will be implemented in phase 2")

    def pull_full(self, source: Source) -> list[Any]:
        raise NotImplementedError("PostgresConnector will be implemented in phase 2")

    def pull_incremental(self, source: Source, checkpoint: str | None) -> list[Any]:
        raise NotImplementedError("PostgresConnector will be implemented in phase 2")

    def normalize(self, source: Source, record: Any) -> DocumentPayload:
        raise NotImplementedError("PostgresConnector will be implemented in phase 2")
