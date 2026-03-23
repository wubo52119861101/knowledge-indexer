from __future__ import annotations

from typing import Any

import httpx

from app.connectors.base import BaseConnector
from app.models.source import Source
from app.schemas.document import AclEntryPayload, DocumentPayload


class ApiConnector(BaseConnector):
    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    def test_connection(self, source: Source) -> bool:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(str(source.config["base_url"]))
            return response.status_code < 500

    def pull_full(self, source: Source) -> list[Any]:
        return self._fetch(source)

    def pull_incremental(self, source: Source, checkpoint: str | None) -> list[Any]:
        return self._fetch(source, checkpoint)

    def normalize(self, source: Source, record: Any) -> DocumentPayload:
        metadata = dict(record.get("metadata") or {})
        metadata.setdefault("updated_at", record.get("updated_at"))
        acl_entries = [
            AclEntryPayload(
                type=acl_item["type"],
                value=acl_item["value"],
                effect=acl_item.get("effect", "allow"),
            )
            for acl_item in record.get("acl", [])
        ]
        return DocumentPayload(
            external_doc_id=str(record["external_doc_id"]),
            title=str(record.get("title") or record["external_doc_id"]),
            content=str(record.get("content") or ""),
            doc_type=str(record.get("doc_type") or "text"),
            metadata=metadata,
            acl=acl_entries,
        )

    def _fetch(self, source: Source, checkpoint: str | None = None) -> list[Any]:
        params = dict(source.config.get("params") or {})
        if checkpoint:
            params["checkpoint"] = checkpoint

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(str(source.config["base_url"]), params=params)
            response.raise_for_status()
            payload = response.json()

        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            items = payload.get("items")
            if isinstance(items, list):
                return items
        raise ValueError("API source response must be a list or an object with 'items'")
