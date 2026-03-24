from __future__ import annotations

from app.core.config import Settings
from app.schemas.retrieval import SearchItem


class NoopAnswerGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.llm_enabled and bool(self.settings.llm_base_url and self.settings.llm_model)

    def generate(self, question: str, evidence_items: list[SearchItem]) -> str | None:
        return None
