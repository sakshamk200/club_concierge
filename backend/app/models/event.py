"""Event data contracts.

``EventRecord`` mirrors the ``public.events`` table column-for-column and is the
canonical structure produced by the Stage 01 Vision-LLM extraction step and
consumed by the Stage 02 RAG layer. ``EventSearchResult`` augments a record with
the cosine similarity score returned by a hybrid vector query.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventRecord(BaseModel):
    """A single structured, semantically indexed event."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = Field(
        default=None,
        description="Server-generated primary key; None before insert.",
    )
    title: str = Field(min_length=1, description="Event title (required).")
    organizer: str | None = Field(default=None, description="Organizing club/body.")
    location: str | None = Field(default=None, description="Venue / room / address.")
    campus: str | None = Field(
        default=None,
        description="Campus scope, e.g. 'UBC' or 'Douglas'.",
    )
    event_timestamp: datetime | None = Field(
        default=None,
        description="Event start, timezone-aware (ISO 8601).",
    )
    registration_deadline: datetime | None = Field(
        default=None,
        description="Registration cutoff, timezone-aware.",
    )
    original_image_url: str | None = Field(
        default=None,
        description="Source flyer image CDN URL (provenance).",
    )
    image_hash: str | None = Field(
        default=None,
        description="SHA-256 of the flyer binary; dedup key.",
    )
    has_free_food: bool = Field(default=False)
    perks: list[str] = Field(
        default_factory=list,
        description="Perk tags such as 'free_food', 'networking'.",
    )
    embedding: list[float] | None = Field(
        default=None,
        description="1536-dim text-embedding-3-small vector.",
    )
    created_at: datetime | None = Field(default=None)


class EventSearchResult(EventRecord):
    """An ``EventRecord`` plus the similarity score from a vector query."""

    similarity: float = Field(
        description="Cosine similarity in [0, 1]; 1.0 == identical direction.",
    )
