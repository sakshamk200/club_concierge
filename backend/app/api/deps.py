"""FastAPI dependency providers.

Async factories that hand request handlers the repositories and services they
need. They resolve the shared connection pool via ``ensure_pool`` so a request
can lazily (re)establish database connectivity if startup creation failed.
"""

from __future__ import annotations

from app.db.events_repo import EventsRepository
from app.db.pool import ensure_pool
from app.services.embeddings import get_embedder
from app.services.retrieval import RetrievalService


async def get_events_repository() -> EventsRepository:
    """Provide an :class:`EventsRepository` bound to the shared pool."""

    return EventsRepository(await ensure_pool())


async def get_retrieval_service() -> RetrievalService:
    """Provide a :class:`RetrievalService` (events repo + configured embedder)."""

    return RetrievalService(
        repo=EventsRepository(await ensure_pool()), embedder=get_embedder()
    )
