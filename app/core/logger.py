from __future__ import annotations

import json
import logging
from typing import Any


DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format=DEFAULT_LOG_FORMAT)



def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)



def log_event(logger: logging.Logger, level: int, event: str, /, **fields: Any) -> None:
    rendered_fields = _render_fields(fields)
    message = event if not rendered_fields else f"{event} {rendered_fields}"
    logger.log(level, message)



def _render_fields(fields: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in sorted(fields):
        value = fields[key]
        if value is None:
            continue
        parts.append(f"{key}={_render_value(value)}")
    return " ".join(parts)



def _render_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False, default=str)
