from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request

from app.api.health import router as health_router
from app.api.internal_ask import router as ask_router
from app.api.internal_search import router as search_router
from app.api.jobs import router as jobs_router
from app.api.sources import router as sources_router
from app.core.config import get_settings
from app.core.logger import configure_logging

configure_logging()
settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-Id", f"req_{uuid4().hex[:12]}")
    response = await call_next(request)
    response.headers["X-Request-Id"] = request.state.request_id
    return response


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "message": "knowledge-indexer is running",
    }


app.include_router(health_router)
app.include_router(sources_router)
app.include_router(jobs_router)
app.include_router(search_router)
app.include_router(ask_router)
