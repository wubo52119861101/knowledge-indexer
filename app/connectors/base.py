from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models.source import Source
from app.schemas.document import DocumentPayload


class BaseConnector(ABC):
    @abstractmethod
    def test_connection(self, source: Source) -> bool:
        raise NotImplementedError

    @abstractmethod
    def pull_full(self, source: Source) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    def pull_incremental(self, source: Source, checkpoint: str | None) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, source: Source, record: Any) -> DocumentPayload:
        raise NotImplementedError
