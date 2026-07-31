"""Shared pytest fixtures.

The integration fixtures attempt a real connection to ``DATABASE_URL`` (the
local Supabase stack by default). When the database is unreachable, the
``db_pool`` fixture skips the dependent tests rather than failing, so the unit
suite still runs in environments without Docker.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio

from app.config import get_settings
from app.db.pool import close_pool, create_pool


async def _database_reachable() -> bool:
    """Return True if a one-off connection to DATABASE_URL succeeds."""

    settings = get_settings()
    try:
        connection = await asyncio.wait_for(
            asyncpg.connect(dsn=settings.database_url), timeout=3.0
        )
    except Exception:
        return False
    await connection.close()
    return True


@pytest_asyncio.fixture
async def db_pool() -> AsyncIterator[asyncpg.Pool]:
    """Function-scoped asyncpg pool; skips the test when no DB is available.

    Function scope keeps the pool bound to the same event loop as the test that
    uses it (pytest-asyncio runs each test in its own loop), avoiding
    "attached to a different loop" errors.
    """

    if not await _database_reachable():
        pytest.skip("DATABASE_URL not reachable; skipping DB integration tests.")

    pool = await create_pool()
    try:
        yield pool
    finally:
        await close_pool()
