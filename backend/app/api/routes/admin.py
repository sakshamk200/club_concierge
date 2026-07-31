"""Admin/demo route: seed the database with sample events."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.api.deps import get_events_repository
from app.config import get_settings
from app.db.events_repo import EventsRepository
from app.db.pool import ensure_pool
from app.ingestion.builder import build_pipeline
from app.seed_data import sample_events
from app.services.embeddings import build_event_embedding_text, get_embedder

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


@router.post("/admin/seed")
async def seed(
    repo: EventsRepository = Depends(get_events_repository),
) -> dict[str, object]:
    """(Re)load the demo event catalogue with freshly computed embeddings.

    Idempotent: existing seed rows (``image_hash`` starting with ``seed-``) are
    removed first so repeated calls converge to the same catalogue.
    """

    logger.debug("seed: clearing existing demo rows")
    pool = await ensure_pool()
    await pool.execute("delete from public.events where image_hash like 'seed-%'")

    embedder = get_embedder()
    events = sample_events()
    texts = [
        build_event_embedding_text(
            e.title, e.organizer, e.location, e.campus, e.perks
        )
        for e in events
    ]
    vectors = await embedder.embed_batch(texts)

    inserted = 0
    for event, vector in zip(events, vectors):
        event.embedding = vector
        await repo.insert_event(event)
        inserted += 1

    logger.debug("seed: inserted %d events", inserted)
    return {"seeded": inserted}


@router.post("/admin/reset-ingested")
async def reset_ingested() -> dict[str, object]:
    """Clear ingested events + dedup ledger so an ingestion run inserts fresh.

    Demo convenience: removes events whose image_hash is a real SHA-256 digest
    (i.e. produced by ingestion, not the 'seed-' catalogue) and empties the
    processed_hashes table. After this, 'Run ingestion' shows '+N new' again.
    """

    pool = await ensure_pool()
    await pool.execute(
        "delete from public.events where image_hash ~ '^[0-9a-f]{64}$'"
    )
    await pool.execute("truncate table public.processed_hashes")
    logger.debug("reset-ingested: cleared ingested events + hashes")
    return {"reset": True}


@router.post("/admin/ingest")
async def ingest() -> dict[str, object]:
    """Run one Stage 01 ingestion pass (scrape → dedup → extract → embed → commit).

    Uses the configured providers (Apify + GPT-4o Vision when keyed, otherwise
    the offline mock providers). Returns per-stage outcome counts. Running it
    twice demonstrates the cryptographic dedup: the second pass inserts 0 and
    reports the posts as duplicates.
    """

    settings = get_settings()
    pipeline = build_pipeline(await ensure_pool(), settings)
    stats = await pipeline.run()
    logger.debug("ingest: %s", stats.as_dict())
    return stats.as_dict()
