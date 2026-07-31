"""FastAPI application entry point.

Wires the lifespan-managed asyncpg pool, CORS for the demo frontend, and the
API routers. Run locally with:

    .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, auth, chat, events, health
from app.config import get_settings
from app.db.pool import close_pool, create_pool
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the connection pool on startup; close it on shutdown."""

    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Starting Club & Event Concierge API")
    try:
        await create_pool(settings)
    except Exception:
        # Boot anyway (the hosted DB may be paused); requests retry lazily
        # via ensure_pool() and the app recovers when the DB returns.
        logger.error("Database unavailable at startup; will retry on demand")
    try:
        yield
    finally:
        await close_pool()
        logger.info("API shutdown complete")


def create_app() -> FastAPI:
    """Application factory."""

    settings = get_settings()
    app = FastAPI(
        title="Club & Event Concierge API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(chat.router)
    app.include_router(admin.router)
    return app


app = create_app()
