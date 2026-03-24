from __future__ import annotations

from collections.abc import Sequence

import httpx

from app.core.config import Settings
from app.core.logger import get_logger
from app.schemas.retrieval import SearchItem

logger = get_logger(__name__)


class AnswerGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.llm_enabled and bool(self.settings.llm_base_url and self.settings.llm_model)

    def generate(self, question: str, evidence_items: list[SearchItem]) -> str | None:
        if not self.enabled or not evidence_items:
            return None

        payload = {
            "model": self.settings.llm_model,
            "messages": self._build_messages(question, evidence_items),
            "question": question,
            "evidence": [
                {
                    "citation_index": index,
                    "chunk_id": item.chunk_id,
                    "document_id": item.document_id,
                    "title": item.document.title,
                    "content": item.content,
                }
                for index, item in enumerate(evidence_items, start=1)
            ],
        }

        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"

        try:
            with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
                response = client.post(self.settings.llm_base_url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("llm generation failed and will fallback: %s", exc)
            return None

        return self._extract_answer(response.json())

    def _build_messages(self, question: str, evidence_items: Sequence[SearchItem]) -> list[dict[str, str]]:
        evidence_text = self._format_evidence(evidence_items)
        return [
            {
                "role": "system",
                "content": (
                    "你是企业知识库问答助手。仅允许基于提供的证据回答；"
                    "若证据不足或存在冲突，请明确说明，不要补充未提供的信息。"
                ),
            },
            {
                "role": "user",
                "content": f"问题：{question}\n\n证据：\n{evidence_text}\n\n请输出简洁、可核验的答案。",
            },
        ]

    def _format_evidence(self, evidence_items: Sequence[SearchItem]) -> str:
        remaining_chars = self.settings.ask_max_context_chars
        segments: list[str] = []

        for index, item in enumerate(evidence_items, start=1):
            content = " ".join(item.content.split())
            prefix = f"[{index}] {item.document.title}: "
            allowed_chars = max(0, remaining_chars - len(prefix))
            snippet = content[:allowed_chars]
            if len(content) > allowed_chars and allowed_chars > 0:
                snippet = f"{snippet.rstrip()}..."
            segment = f"{prefix}{snippet}" if snippet else prefix.rstrip()
            if not segment:
                continue
            segments.append(segment)
            remaining_chars -= len(segment)
            if remaining_chars <= 0:
                break

        return "\n".join(segments)

    def _extract_answer(self, payload: object) -> str | None:
        if isinstance(payload, str):
            return payload.strip() or None
        if not isinstance(payload, dict):
            return None

        direct_value = self._extract_first_string(
            payload,
            ("answer", "output_text", "text", "content"),
        )
        if direct_value is not None:
            return direct_value

        data = payload.get("data")
        if isinstance(data, dict):
            nested_value = self._extract_first_string(
                data,
                ("answer", "output_text", "text", "content"),
            )
            if nested_value is not None:
                return nested_value

        choices = payload.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
                text = choice.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()

        return None

    @staticmethod
    def _extract_first_string(data: dict[str, object], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None


class NoopAnswerGenerator(AnswerGenerator):
    pass
