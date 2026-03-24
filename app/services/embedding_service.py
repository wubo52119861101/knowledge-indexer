from __future__ import annotations

import hashlib
import math
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.utils import tokenize


class EmbeddingService(Protocol):
    def embed(self, text: str) -> list[float]: ...


class HashEmbeddingService:
    def __init__(self, dimension: int = 64) -> None:
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        tokens = tokenize(text)
        vector = [0.0] * self.dimension
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class HttpEmbeddingService:
    def __init__(
        self,
        api_url: str,
        *,
        timeout_seconds: float = 10.0,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds
        self.model = model
        self.api_key = api_key

    def embed(self, text: str) -> list[float]:
        payload: dict[str, Any] = {"input": text}
        if self.model:
            payload["model"] = self.model

        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = httpx.post(self.api_url, json=payload, headers=headers, timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()
        return self._extract_embedding(data)

    def _extract_embedding(self, payload: Any) -> list[float]:
        if isinstance(payload, dict):
            if isinstance(payload.get("embedding"), list):
                return [float(item) for item in payload["embedding"]]
            data = payload.get("data")
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, dict) and isinstance(first.get("embedding"), list):
                    return [float(item) for item in first["embedding"]]
            if isinstance(payload.get("vector"), list):
                return [float(item) for item in payload["vector"]]
        raise ValueError("embedding provider response does not contain a valid embedding vector")


def build_embedding_service(settings: Settings) -> EmbeddingService:
    provider = settings.embedding_provider.lower().strip()
    if provider == "hash":
        return HashEmbeddingService(dimension=settings.embedding_dimension)
    if provider in {"http", "remote"}:
        if not settings.embedding_api_url:
            raise ValueError("EMBEDDING_API_URL 未配置，无法启用 http embedding provider")
        return HttpEmbeddingService(
            api_url=settings.embedding_api_url,
            timeout_seconds=settings.embedding_timeout_seconds,
            model=settings.embedding_model,
            api_key=settings.embedding_api_key,
        )
    raise ValueError(f"unsupported embedding provider: {settings.embedding_provider}")
