"""Health check route."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.db.pool import ensure_pool

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, object]:
    """Report liveness and database connectivity."""

    db_ok = False
    try:
        pool = await ensure_pool()
        value = await pool.fetchval("select 1")
        db_ok = value == 1
    except Exception:
        logger.error("Health check DB probe failed", exc_info=True)
        db_ok = False

    return {"status": "ok", "database": "up" if db_ok else "down"}
