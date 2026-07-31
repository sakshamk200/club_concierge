"""Pipeline construction helper.

Assembles an :class:`IngestionPipeline` from configuration and the shared
connection pool, wiring the configured source adapters and the embedder.
"""

from __future__ import annotations

import asyncpg

from app.config import Settings, get_settings
from app.db.events_repo import EventsRepository
from app.db.hashes_repo import HashesRepository
from app.ingestion.pipeline import IngestionPipeline
from app.integrations.sources.factory import get_sources
from app.services.embeddings import get_embedder


def build_pipeline(
    pool: asyncpg.Pool, settings: Settings | None = None
) -> IngestionPipeline:
    """Construct an ingestion pipeline bound to ``pool``."""

    settings = settings or get_settings()
    return IngestionPipeline(
        sources=get_sources(settings),
        embedder=get_embedder(settings),
        events_repo=EventsRepository(pool),
        hashes_repo=HashesRepository(pool),
        free_only=settings.free_events_only,
        per_source_limit=settings.scrape_per_source_limit,
    )
