"""Retrieval service.

Bridges the embedding provider and the events repository to perform the
Stage 02 hybrid query: embed the natural-language query, then run cosine
similarity ranking combined with structured metadata filters (campus boundary,
free-food / perks, time window).
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.db.events_repo import EventsRepository
from app.models.event import EventSearchResult
from app.services.embeddings import Embedder

logger = logging.getLogger(__name__)

# Minimum cosine similarity for a result to count as a real semantic match.
_MIN_SIMILARITY = 0.12


class RetrievalService:
    """Embed queries and run hybrid vector + metadata search."""

    def __init__(self, repo: EventsRepository, embedder: Embedder) -> None:
        self._repo = repo
        self._embedder = embedder

    async def search(
        self,
        query: str,
        *,
        limit: int = 6,
        campus: str | None = None,
        require_free_food: bool = False,
        starts_after: datetime | None = None,
        starts_before: datetime | None = None,
        interests: list[str] | None = None,
    ) -> list[EventSearchResult]:
        """Return the top events for a natural-language query under filters.

        Args:
            query: Free-text student query.
            limit: Maximum results to return.
            campus: Restrict to this campus when provided.
            require_free_food: Keep only free-food events when True.
            starts_after: Lower bound on event start time.
            starts_before: Upper bound on event start time.
            interests: Student profile interests; used to gently bias the query
                vector toward preferred topics (preference-aware ranking).
        """

        logger.debug("RetrievalService.search query=%r campus=%s", query, campus)
        # Preference-aware: fold the student's interests into the query text so
        # semantically related events rank higher, without overriding the ask.
        search_text = query
        if interests:
            search_text = f"{query}. Interested in: {', '.join(interests)}"
        query_vector = await self._embedder.embed_text(search_text)
        results = await self._repo.semantic_search(
            query_vector,
            limit=max(limit, 12),
            campus=campus,
            require_free_food=require_free_food,
            starts_after=starts_after,
            starts_before=starts_before,
        )
        strong = [r for r in results if r.similarity >= _MIN_SIMILARITY]

        if not strong:
            logger.debug("No strong matches; falling back to upcoming-by-date")
            strong = await self._repo.list_upcoming(
                limit=max(limit, 12),
                campus=campus,
                require_free_food=require_free_food,
                starts_after=starts_after,
                starts_before=starts_before,
            )

        strong = _rerank_by_interest(strong, interests)[:limit]
        logger.debug("RetrievalService.search returned %d results", len(strong))
        return strong

    async def upcoming(
        self,
        *,
        limit: int = 12,
        campus: str | None = None,
        require_free_food: bool = False,
        interests: list[str] | None = None,
    ) -> list[EventSearchResult]:
        """Upcoming events for browse views, optionally personalised by interest."""

        pool_size = max(limit * 2, 16) if interests else limit
        events = await self._repo.list_upcoming(
            limit=pool_size, campus=campus, require_free_food=require_free_food
        )
        return _rerank_by_interest(events, interests)[:limit]


def _rerank_by_interest(
    events: list[EventSearchResult], interests: list[str] | None
) -> list[EventSearchResult]:
    """Stably bump events whose text matches the student's interests.

    A small preference boost is added to the sort key so relevant events move
    up without discarding the underlying similarity / recency ordering.
    """

    if not interests:
        return events
    terms = [i.strip().lower() for i in interests if i.strip()]
    if not terms:
        return events

    def boost(ev: EventSearchResult) -> int:
        blob = f"{ev.title} {ev.organizer or ''} {' '.join(ev.perks)}".lower()
        return sum(1 for t in terms if t in blob)

    # Sort by interest matches first (desc), preserving the existing order
    # (Python's sort is stable) for events with equal matches.
    return sorted(events, key=boost, reverse=True)
