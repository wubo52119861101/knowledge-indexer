from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.logger import get_logger
from app.schemas.retrieval import SearchItem

logger = get_logger(__name__)


class RerankService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.rerank_enabled and bool(self.settings.rerank_base_url)

    def rerank(self, query: str, items: list[SearchItem]) -> tuple[list[SearchItem], bool]:
        if not self.enabled or len(items) <= 1:
            return items, False

        payload = {
            "query": query,
            "top_n": min(len(items), self.settings.rerank_top_n),
            "documents": [
                {
                    "id": item.chunk_id,
                    "content": item.content,
                    "score": item.score,
                    "title": item.document.title,
                }
                for item in items
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.settings.rerank_api_key:
            headers["Authorization"] = f"Bearer {self.settings.rerank_api_key}"

        try:
            with httpx.Client(timeout=self.settings.rerank_timeout_seconds) as client:
                response = client.post(self.settings.rerank_base_url, json=payload, headers=headers)
                response.raise_for_status()
                reranked_items = self._extract_ranked_items(response.json(), items)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("rerank failed and will fallback to retrieval order: %s", exc)
            return items, False

        return reranked_items, True

    def _extract_ranked_items(self, payload: object, items: list[SearchItem]) -> list[SearchItem]:
        if not isinstance(payload, dict):
            raise ValueError("rerank response must be a JSON object")

        result_candidates = [payload.get("results"), payload.get("items")]
        data = payload.get("data")
        if isinstance(data, dict):
            result_candidates.extend([data.get("results"), data.get("items")])

        results = next((candidate for candidate in result_candidates if isinstance(candidate, list)), None)
        if not results:
            raise ValueError("rerank response does not contain ranking results")

        items_by_chunk_id = {item.chunk_id: item for item in items}
        ordered_items: list[SearchItem] = []
        seen_chunk_ids: set[str] = set()

        for index, result in enumerate(results):
            if not isinstance(result, dict):
                continue
            item = self._resolve_item(result, index, items, items_by_chunk_id)
            if item is None or item.chunk_id in seen_chunk_ids:
                continue
            ordered_items.append(item)
            seen_chunk_ids.add(item.chunk_id)

        if not ordered_items:
            raise ValueError("rerank response does not map to known items")

        ordered_items.extend(item for item in items if item.chunk_id not in seen_chunk_ids)
        return ordered_items

    @staticmethod
    def _resolve_item(
        result: dict[str, object],
        index: int,
        items: list[SearchItem],
        items_by_chunk_id: dict[str, SearchItem],
    ) -> SearchItem | None:
        for key in ("id", "chunk_id", "document_id", "documentId"):
            value = result.get(key)
            if isinstance(value, str) and value in items_by_chunk_id:
                return items_by_chunk_id[value]

        ranked_index = result.get("index")
        if isinstance(ranked_index, int) and 0 <= ranked_index < len(items):
            return items[ranked_index]
        if 0 <= index < len(items):
            return items[index]
        return None


class NoopRerankService(RerankService):
    pass
