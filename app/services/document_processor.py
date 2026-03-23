from __future__ import annotations

import re

from app.core.utils import tokenize


class DocumentProcessor:
    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def clean_text(self, text: str) -> str:
        cleaned = text.replace("\r\n", "\n")
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        return cleaned.strip()

    def split_text(self, text: str) -> list[str]:
        normalized = self.clean_text(text)
        if not normalized:
            return []
        if len(normalized) <= self.chunk_size:
            return [normalized]

        chunks: list[str] = []
        start = 0
        step = self.chunk_size - self.chunk_overlap
        while start < len(normalized):
            end = min(len(normalized), start + self.chunk_size)
            window = normalized[start:end]
            if end < len(normalized):
                paragraph_break = window.rfind("\n\n")
                if paragraph_break > self.chunk_size // 2:
                    end = start + paragraph_break
                    window = normalized[start:end]
            chunks.append(window.strip())
            if end >= len(normalized):
                break
            start = max(start + step, end - self.chunk_overlap)
        return [chunk for chunk in chunks if chunk]

    def summarize(self, text: str, max_length: int = 120) -> str:
        summary = self.clean_text(text).replace("\n", " ")
        return summary[:max_length]

    def estimate_token_count(self, text: str) -> int:
        return len(tokenize(text))
