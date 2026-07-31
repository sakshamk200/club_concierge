"""UBC AMS adapter — "The Events Calendar" WordPress REST API.

Pulls real, structured, upcoming events from the AMS events calendar. Free
events are detected from the ``cost`` field by the downstream classifier.
"""

from __future__ import annotations

import logging

import httpx

from app.integrations.sources.base import RawEvent
from app.integrations.sources.util import parse_naive_utc, strip_html

logger = logging.getLogger(__name__)


class TheEventsCalendarAdapter:
    """Adapter for a WordPress "The Events Calendar" REST endpoint."""

    def __init__(
        self,
        api_url: str,
        *,
        name: str = "ubc_ams",
        campus: str = "UBC",
        default_organizer: str = "AMS UBC",
    ) -> None:
        self.name = name
        self._api_url = api_url
        self._campus = campus
        self._default_organizer = default_organizer

    async def fetch(self, limit: int) -> list[RawEvent]:
        """Fetch upcoming events from the API (single page up to ``limit``)."""

        params = {"per_page": min(limit, 50), "page": 1, "status": "publish"}
        logger.debug("TheEventsCalendarAdapter fetching %s", self._api_url)
        try:
            async with httpx.AsyncClient(
                timeout=30.0, headers={"User-Agent": "ClubConcierge/0.1"}
            ) as client:
                response = await client.get(self._api_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            logger.error("AMS events fetch failed", exc_info=True)
            raise

        events: list[RawEvent] = []
        for item in payload.get("events", [])[:limit]:
            events.append(self._to_raw_event(item))
        logger.debug("TheEventsCalendarAdapter parsed %d events", len(events))
        return events

    def _to_raw_event(self, item: dict[str, object]) -> RawEvent:
        venue = item.get("venue") or {}
        location = None
        if isinstance(venue, dict):
            parts = [venue.get("venue"), venue.get("address"), venue.get("city")]
            location = ", ".join(str(p) for p in parts if p) or None

        organizer = self._default_organizer
        org_field = item.get("organizer")
        if isinstance(org_field, list) and org_field:
            first = org_field[0]
            if isinstance(first, dict) and first.get("organizer"):
                organizer = strip_html(str(first["organizer"])) or organizer

        return RawEvent(
            source=self.name,
            external_id=str(item.get("id") or item.get("global_id") or item.get("url")),
            title=strip_html(str(item.get("title", ""))) or "Untitled Event",
            url=item.get("url") if isinstance(item.get("url"), str) else None,
            organizer=organizer,
            location=location,
            campus=self._campus,
            start=parse_naive_utc(_as_str(item.get("utc_start_date"))),
            end=parse_naive_utc(_as_str(item.get("utc_end_date"))),
            cost_text=_as_str(item.get("cost")),
            description=strip_html(_as_str(item.get("excerpt"))),
        )


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
