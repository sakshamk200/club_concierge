"""Offline fallback adapter backed by bundled fixtures.

Replays the sample posts as structured RawEvents so ingestion runs with no
network. Used when ``USE_MOCK_SOURCES`` is set, or as an automatic fallback
when live sources return nothing.
"""

from __future__ import annotations

import logging

from app.ingestion.fixtures import fixture_posts
from app.integrations.sources.base import RawEvent
from app.models.event import EventRecord

logger = logging.getLogger(__name__)


class MockSourceAdapter:
    """Yields fixture events as already-structured RawEvents."""

    name = "mock"

    async def fetch(self, limit: int) -> list[RawEvent]:
        events: list[RawEvent] = []
        for raw in fixture_posts()[:limit]:
            ev: EventRecord = raw["event"]  # type: ignore[assignment]
            cost = "free" if ev.has_free_food else ""
            events.append(
                RawEvent(
                    source=self.name,
                    external_id=str(raw["post_id"]),
                    title=ev.title,
                    url=str(raw["image_url"]),
                    organizer=ev.organizer,
                    location=ev.location,
                    campus=ev.campus,
                    start=ev.event_timestamp,
                    end=None,
                    cost_text=cost,
                    description=" ".join(ev.perks),
                )
            )
        logger.debug("MockSourceAdapter produced %d events", len(events))
        return events
