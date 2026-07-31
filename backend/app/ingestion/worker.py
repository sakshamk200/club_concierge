"""Background ingestion worker.

Runs the Stage 01 pipeline on a fixed APScheduler cadence, independent of user
activity. Uses a lifespan-style async context for the connection pool and a
graceful shutdown on SIGINT/SIGTERM.

Run with:
    .venv/Scripts/python -m app.ingestion.worker
"""

from __future__ import annotations

import asyncio
import logging
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.db.pool import close_pool, create_pool
from app.ingestion.builder import build_pipeline
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)


async def run_once() -> dict[str, int]:
    """Create a pool, run one ingestion pass, and tear the pool down."""

    settings = get_settings()
    pool = await create_pool(settings)
    try:
        pipeline = build_pipeline(pool, settings)
        stats = await pipeline.run()
        return stats.as_dict()
    finally:
        await close_pool()


async def _serve() -> None:
    """Run the scheduler until a shutdown signal is received."""

    settings = get_settings()
    configure_logging(settings.log_level)
    pool = await create_pool(settings)
    pipeline = build_pipeline(pool, settings)

    async def job() -> None:
        try:
            await pipeline.run()
        except Exception:
            logger.error("Scheduled ingestion job failed", exc_info=True)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        job,
        "interval",
        minutes=settings.ingestion_interval_minutes,
        next_run_time=None,
    )
    scheduler.start()
    logger.info(
        "Ingestion worker started (every %d min). Running initial pass...",
        settings.ingestion_interval_minutes,
    )
    await job()  # immediate first run

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            # add_signal_handler is unsupported on Windows ProactorEventLoop.
            pass

    try:
        await stop.wait()
    finally:
        scheduler.shutdown(wait=False)
        await close_pool()
        logger.info("Ingestion worker stopped")


def main() -> None:
    """Entry point for ``python -m app.ingestion.worker``."""

    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
