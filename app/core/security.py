from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def verify_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.internal_api_token:
        return
    if x_internal_token != settings.internal_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid internal token",
        )
