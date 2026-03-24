from __future__ import annotations

from typing import Any


def build_health_payload(
    *,
    status: str,
    detail: str,
    configuration: str,
    connectivity: str,
    capability: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "detail": detail,
        "layers": {
            "configuration": configuration,
            "connectivity": connectivity,
            "capability": capability,
        },
    }
    if extra:
        payload.update(extra)
    return payload



def short_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__
