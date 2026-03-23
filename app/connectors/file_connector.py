from __future__ import annotations

from pathlib import Path
from typing import Any

from app.connectors.base import BaseConnector
from app.models.source import Source
from app.schemas.document import DocumentPayload


class FileConnector(BaseConnector):
    def test_connection(self, source: Source) -> bool:
        root_path = source.config.get("root_path", "")
        return Path(root_path).exists()

    def pull_full(self, source: Source) -> list[Path]:
        return self._scan_files(source)

    def pull_incremental(self, source: Source, checkpoint: str | None) -> list[Path]:
        files = self._scan_files(source)
        if not checkpoint:
            return files
        threshold = float(checkpoint)
        return [file_path for file_path in files if file_path.stat().st_mtime > threshold]

    def normalize(self, source: Source, record: Any) -> DocumentPayload:
        file_path = Path(record)
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        return DocumentPayload(
            external_doc_id=file_path.as_posix(),
            title=file_path.stem,
            content=content,
            doc_type=file_path.suffix.lstrip(".") or "text",
            metadata={
                "path": file_path.as_posix(),
                "updated_at": file_path.stat().st_mtime,
            },
        )

    def _scan_files(self, source: Source) -> list[Path]:
        root_path = Path(source.config["root_path"])
        patterns = source.config.get("file_patterns", ["**/*.md", "**/*.txt"])
        results: list[Path] = []
        seen: set[Path] = set()
        for pattern in patterns:
            for file_path in root_path.glob(pattern):
                if file_path.is_file() and file_path not in seen:
                    seen.add(file_path)
                    results.append(file_path)
        return sorted(results)
