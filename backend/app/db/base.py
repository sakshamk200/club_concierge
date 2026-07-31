"""Shared repository base.

Provides a thin, well-logged wrapper around an :class:`asyncpg.Pool` so that
concrete repositories focus on SQL rather than connection/error boilerplate.
Each public I/O method logs at the boundary (DEBUG entry, ERROR with
``exc_info`` on failure), per project conventions.
"""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base class holding a pool reference and common query helpers."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def _execute(self, query: str, *args: Any) -> str:
        """Run a statement that returns a status tag (INSERT/UPDATE/DELETE)."""

        logger.debug("execute: %s", _summarize(query))
        try:
            async with self._pool.acquire() as connection:
                return await connection.execute(query, *args)
        except Exception:
            logger.error("execute failed: %s", _summarize(query), exc_info=True)
            raise

    async def _fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        """Run a query and return all rows."""

        logger.debug("fetch: %s", _summarize(query))
        try:
            async with self._pool.acquire() as connection:
                return await connection.fetch(query, *args)
        except Exception:
            logger.error("fetch failed: %s", _summarize(query), exc_info=True)
            raise

    async def _fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        """Run a query and return the first row, or ``None``."""

        logger.debug("fetchrow: %s", _summarize(query))
        try:
            async with self._pool.acquire() as connection:
                return await connection.fetchrow(query, *args)
        except Exception:
            logger.error("fetchrow failed: %s", _summarize(query), exc_info=True)
            raise

    async def _fetchval(self, query: str, *args: Any) -> Any:
        """Run a query and return a single scalar value."""

        logger.debug("fetchval: %s", _summarize(query))
        try:
            async with self._pool.acquire() as connection:
                return await connection.fetchval(query, *args)
        except Exception:
            logger.error("fetchval failed: %s", _summarize(query), exc_info=True)
            raise


def _summarize(query: str) -> str:
    """Collapse a SQL string to a single compact line for log output."""

    return " ".join(query.split())
