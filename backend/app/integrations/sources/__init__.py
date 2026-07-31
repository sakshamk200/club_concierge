"""Event source adapters.

A source-agnostic ingestion design: every adapter implements the
:class:`SourceAdapter` protocol and yields normalised :class:`RawEvent` records.
The downstream pipeline (dedup -> free-filter -> validate -> embed -> store) is
identical regardless of where the event came from.

Adapters:
* :class:`TheEventsCalendarAdapter` — WordPress "The Events Calendar" REST API
  (UBC AMS). Real HTTP, no credentials.
* :class:`SquarespaceEventsAdapter` — Squarespace events collection JSON
  (Douglas Students' Union). Real HTTP, no credentials.
* :class:`MockSourceAdapter` — bundled fixtures for fully offline runs.
"""

from __future__ import annotations

from app.integrations.sources.base import RawEvent, SourceAdapter
from app.integrations.sources.factory import get_sources
from app.integrations.sources.livewhale import LiveWhaleAdapter
from app.integrations.sources.mock_source import MockSourceAdapter
from app.integrations.sources.squarespace_events import SquarespaceEventsAdapter
from app.integrations.sources.the_events_calendar import TheEventsCalendarAdapter

__all__ = [
    "RawEvent",
    "SourceAdapter",
    "get_sources",
    "LiveWhaleAdapter",
    "MockSourceAdapter",
    "SquarespaceEventsAdapter",
    "TheEventsCalendarAdapter",
]
