"""SFU adapter — LiveWhale calendar JSON feed.

SFU's events calendar (events.sfu.ca) runs LiveWhale, which exposes a public
JSON feed of events. Returns real, structured SFU events. The feed is large and
contains recurring entries, so this adapter de-duplicates by title (keeping the
earliest) before returning.
"""

from __future__ import annotations

import logging

import httpx

from app.integrations.sources.base import RawEvent
from app.integrations.sources.util import parse_iso_date, strip_html

logger = logging.getLogger(__name__)


class LiveWhaleAdapter:
    """Adapter for a LiveWhale ``/live/json/events`` feed."""

    def __init__(
        self,
        feed_url: str,
        *,
        name: str = "sfu_livewhale",
        campus: str = "SFU",
        default_organizer: str = "SFU",
    ) -> None:
        self.name = name
        self._feed_url = feed_url
        self._campus = campus
        self._default_organizer = default_organizer

    async def fetch(self, limit: int) -> list[RawEvent]:
        logger.debug("LiveWhaleAdapter fetching %s", self._feed_url)
        try:
            async with httpx.AsyncClient(
                timeout=60.0, headers={"User-Agent": "Mozilla/5.0 (ClubConcierge)"}
            ) as client:
                response = await client.get(self._feed_url)
                response.raise_for_status()
                items = response.json()
        except Exception:
            logger.error("SFU LiveWhale fetch failed", exc_info=True)
            raise

        if not isinstance(items, list):
            items = items.get("data") or items.get("events") or []

        # De-duplicate by title (the feed expands recurring events) and cap.
        seen: set[str] = set()
        events: list[RawEvent] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = strip_html(str(item.get("title", ""))) or "Untitled Event"
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            events.append(self._to_raw_event(item, title))
            if len(events) >= limit:
                break

        logger.debug("LiveWhaleAdapter parsed %d events", len(events))
        return events

    def _to_raw_event(self, item: dict[str, object], title: str) -> RawEvent:
        location = (
            _as_str(item.get("location_title"))
            or _as_str(item.get("location"))
        )
        organizer = _as_str(item.get("group_title")) or self._default_organizer
        return RawEvent(
            source=self.name,
            external_id=str(item.get("id") or item.get("url") or title),
            title=title,
            url=_as_str(item.get("url")),
            organizer=organizer,
            location=location,
            campus=self._campus,
            start=parse_iso_date(_as_str(item.get("date_iso"))),
            end=parse_iso_date(_as_str(item.get("date2_iso"))),
            cost_text=_as_str(item.get("cost")),
            description=strip_html(_as_str(item.get("description"))),
        )


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
