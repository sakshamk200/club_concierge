"""asyncpg connection pool lifecycle.

The pool is created once during the FastAPI/worker lifespan and shared by every
repository. Each pooled connection registers the pgvector codec so Python
``list[float]`` values bind directly to the ``vector`` column type.
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg
from pgvector.asyncpg import register_vector

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_pool_lock: asyncio.Lock = asyncio.Lock()


async def _init_connection(connection: asyncpg.Connection) -> None:
    """Per-connection initialiser run by asyncpg for every pooled connection.

    Registers the pgvector type codec so ``vector`` columns round-trip as
    Python lists / numpy arrays.
    """

    await register_vector(connection)


async def create_pool(settings: Settings | None = None) -> asyncpg.Pool:
    """Create (idempotently) and return the process-wide connection pool.

    Args:
        settings: Optional settings override; defaults to the cached singleton.

    Returns:
        The live :class:`asyncpg.Pool`.
    """

    global _pool

    if _pool is not None:
        return _pool

    settings = settings or get_settings()
    logger.debug(
        "Creating asyncpg pool (min=%s, max=%s)",
        settings.db_pool_min_size,
        settings.db_pool_max_size,
    )
    try:
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            command_timeout=settings.db_command_timeout,
            init=_init_connection,
        )
    except Exception:
        logger.error("Failed to create asyncpg pool", exc_info=True)
        raise

    logger.debug("asyncpg pool created")
    return _pool


def get_pool() -> asyncpg.Pool:
    """Return the already-created pool.

    Raises:
        RuntimeError: If :func:`create_pool` has not been called yet.
    """

    if _pool is None:
        raise RuntimeError(
            "Connection pool not initialised; call create_pool() during startup."
        )
    return _pool


async def ensure_pool(settings: Settings | None = None) -> asyncpg.Pool:
    """Return the pool, creating it on demand if startup creation failed.

    Lets the API boot while the database is briefly unavailable (e.g. a paused
    hosted instance) and recover automatically on the first request after the
    database comes back.
    """

    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is not None:
            return _pool
        return await create_pool(settings)


async def close_pool() -> None:
    """Gracefully close the pool during shutdown (idempotent)."""

    global _pool

    if _pool is None:
        return

    logger.debug("Closing asyncpg pool")
    try:
        await _pool.close()
    except Exception:
        logger.error("Error while closing asyncpg pool", exc_info=True)
        raise
    finally:
        _pool = None

    logger.debug("asyncpg pool closed")
