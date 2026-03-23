from __future__ import annotations

from fastapi import Request


def success_response(request: Request, data, message: str = "ok") -> dict:
    return {
        "code": 0,
        "message": message,
        "data": data,
        "request_id": request.state.request_id,
    }
