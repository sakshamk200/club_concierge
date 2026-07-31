"""Events repository.

CRUD plus the Stage 02 hybrid query: cosine-similarity vector ranking combined
with structured metadata filters (campus boundary, temporal range, free-food /
perk membership). All queries run through the well-logged
:class:`~app.db.base.BaseRepository` helpers.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

import asyncpg

from app.db.base import BaseRepository
from app.models.event import EventRecord, EventSearchResult

logger = logging.getLogger(__name__)

# Column list shared by row-returning queries (keeps SELECT and mapping in sync).
_COLUMNS = (
    "id, title, organizer, location, campus, event_timestamp, "
    "registration_deadline, original_image_url, image_hash, has_free_food, "
    "perks, embedding, created_at"
)


class EventsRepository(BaseRepository):
    """Data access for ``public.events``."""

    async def insert_event(self, event: EventRecord) -> EventRecord:
        """Atomically insert one event (structured fields + embedding vector).

        Args:
            event: The validated record to persist. ``id``/``created_at`` are
                ignored on input and populated from the database row.

        Returns:
            The persisted record with server-generated fields filled in.
        """

        query = f"""
            insert into public.events (
                title, organizer, location, campus, event_timestamp,
                registration_deadline, original_image_url, image_hash,
                has_free_food, perks, embedding
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            returning {_COLUMNS}
        """
        row = await self._fetchrow(
            query,
            event.title,
            event.organizer,
            event.location,
            event.campus,
            event.event_timestamp,
            event.registration_deadline,
            event.original_image_url,
            event.image_hash,
            event.has_free_food,
            event.perks,
            event.embedding,
        )
        # insert ... returning always yields a row on success.
        assert row is not None
        return _row_to_event(row)

    async def get_by_id(self, event_id: UUID) -> EventRecord | None:
        """Fetch a single event by primary key, or ``None`` if absent."""

        query = f"select {_COLUMNS} from public.events where id = $1"
        row = await self._fetchrow(query, event_id)
        return _row_to_event(row) if row is not None else None

    async def image_hash_exists(self, image_hash: str) -> bool:
        """Return whether an event with the given SHA-256 image hash exists."""

        query = "select exists(select 1 from public.events where image_hash = $1)"
        return bool(await self._fetchval(query, image_hash))

    async def semantic_search(
        self,
        query_embedding: list[float],
        *,
        limit: int = 10,
        campus: str | None = None,
        starts_after: datetime | None = None,
        starts_before: datetime | None = None,
        require_free_food: bool = False,
        required_perks: list[str] | None = None,
    ) -> list[EventSearchResult]:
        """Hybrid vector + metadata search.

        Ranks by cosine similarity to ``query_embedding`` while enforcing
        structured filters so, e.g., a UBC-scoped query cannot surface Douglas
        College events.

        Args:
            query_embedding: 1536-dim query vector.
            limit: Maximum number of results (top-K).
            campus: Restrict to this campus when provided.
            starts_after: Keep events starting at/after this instant.
            starts_before: Keep events starting at/before this instant.
            require_free_food: When True, keep only free-food events.
            required_perks: When provided, keep events whose ``perks`` contain
                all of these tags.

        Returns:
            Up to ``limit`` results ordered by descending similarity.
        """

        # Build the predicate list dynamically; $1 is always the query vector.
        params: list[object] = [query_embedding]
        predicates: list[str] = ["embedding is not null"]

        if campus is not None:
            params.append(campus)
            predicates.append(f"campus = ${len(params)}")
        if starts_after is not None:
            params.append(starts_after)
            predicates.append(f"event_timestamp >= ${len(params)}")
        if starts_before is not None:
            params.append(starts_before)
            predicates.append(f"event_timestamp <= ${len(params)}")
        if require_free_food:
            predicates.append("has_free_food = true")
        if required_perks:
            params.append(required_perks)
            predicates.append(f"perks @> ${len(params)}")

        params.append(limit)
        limit_pos = len(params)

        where_clause = " and ".join(predicates)
        query = f"""
            select {_COLUMNS}, 1 - (embedding <=> $1) as similarity
            from public.events
            where {where_clause}
            order by embedding <=> $1
            limit ${limit_pos}
        """
        rows = await self._fetch(query, *params)
        return [_row_to_search_result(row) for row in rows]

    async def list_upcoming(
        self,
        *,
        limit: int = 6,
        campus: str | None = None,
        require_free_food: bool = False,
        starts_after: datetime | None = None,
        starts_before: datetime | None = None,
    ) -> list[EventSearchResult]:
        """List soonest upcoming events (browse mode; ordered by start time).

        An optional [``starts_after``, ``starts_before``] window narrows results
        to a specific period (e.g. tomorrow, this weekend).
        """

        params: list[object] = []
        predicates = ["event_timestamp is not null"]
        # Default lower bound is "now"; an explicit starts_after overrides it.
        if starts_after is not None:
            params.append(starts_after)
            predicates.append(f"event_timestamp >= ${len(params)}")
        else:
            predicates.append("event_timestamp >= now()")
        if starts_before is not None:
            params.append(starts_before)
            predicates.append(f"event_timestamp <= ${len(params)}")
        if campus is not None:
            params.append(campus)
            predicates.append(f"campus = ${len(params)}")
        if require_free_food:
            predicates.append("has_free_food = true")
        params.append(limit)
        limit_pos = len(params)

        where_clause = " and ".join(predicates)
        query = f"""
            select {_COLUMNS}, 1.0 as similarity
            from public.events
            where {where_clause}
            order by event_timestamp asc
            limit ${limit_pos}
        """
        rows = await self._fetch(query, *params)
        return [_row_to_search_result(row) for row in rows]

    async def delete_by_id(self, event_id: UUID) -> bool:
        """Delete an event by id; return True if a row was removed."""

        status = await self._execute(
            "delete from public.events where id = $1", event_id
        )
        return status.endswith("1")


def _row_to_event(row: asyncpg.Record) -> EventRecord:
    """Map a database row to an :class:`EventRecord`."""

    data = dict(row)
    embedding = data.get("embedding")
    if embedding is not None:
        # pgvector returns a numpy array; normalise to a plain list of floats.
        embedding = [float(value) for value in embedding]
    data["embedding"] = embedding
    return EventRecord.model_validate(data)


def _row_to_search_result(row: asyncpg.Record) -> EventSearchResult:
    """Map a database row (with a ``similarity`` column) to a search result."""

    data = dict(row)
    embedding = data.get("embedding")
    if embedding is not None:
        embedding = [float(value) for value in embedding]
    data["embedding"] = embedding
    data["similarity"] = float(data["similarity"])
    return EventSearchResult.model_validate(data)
