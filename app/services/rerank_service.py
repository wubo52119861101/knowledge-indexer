from __future__ import annotations

from app.core.config import Settings
from app.schemas.retrieval import SearchItem


class NoopRerankService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.rerank_enabled and bool(self.settings.rerank_base_url)

    def rerank(self, query: str, items: list[SearchItem]) -> list[SearchItem]:
        return items
