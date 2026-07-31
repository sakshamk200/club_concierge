"""Apply SQL migrations to the configured database.

Reads ``DATABASE_URL`` (via app.config settings / .env) and applies every
``supabase/migrations/*.sql`` file in lexicographic order, each in its own
transaction. Safe to re-run: the migrations use ``if not exists`` / idempotent
guards. This is the Docker-free path for applying schema to a hosted Supabase
project (the local CLI stack requires Docker).

Usage (from /backend):
    .venv/Scripts/python scripts/apply_migrations.py
"""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import sys

# Ensure the backend package root is importable when run as a script file.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

from app.config import get_settings
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)

_MIGRATIONS_GLOB = os.path.join(
    os.path.dirname(__file__), "..", "supabase", "migrations", "*.sql"
)


async def apply_all() -> None:
    """Apply every migration file in order against ``DATABASE_URL``."""

    settings = get_settings()
    files = sorted(glob.glob(_MIGRATIONS_GLOB))
    if not files:
        logger.warning("No migration files found at %s", _MIGRATIONS_GLOB)
        return

    # statement_cache_size=0 keeps us compatible with pgbouncer-style poolers.
    connection = await asyncpg.connect(
        dsn=settings.database_url, statement_cache_size=0
    )
    try:
        for path in files:
            name = os.path.basename(path)
            with open(path, encoding="utf-8") as handle:
                sql = handle.read()
            logger.info("Applying migration %s", name)
            try:
                async with connection.transaction():
                    await connection.execute(sql)
            except Exception:
                logger.error("Migration %s failed", name, exc_info=True)
                raise
            logger.info("Applied %s", name)
    finally:
        await connection.close()

    logger.info("All migrations applied successfully")


def main() -> None:
    """Entry point."""

    settings = get_settings()
    configure_logging(settings.log_level)
    asyncio.run(apply_all())


if __name__ == "__main__":
    main()
