"""Douglas Students' Union adapter — Squarespace events collection.

Squarespace exposes any collection page as JSON via ``?format=json``. The DSU
events page returns ``upcoming`` (and ``past``) arrays of event items. Most DSU
events are free; the classifier treats a missing cost as free.
"""

from __future__ import annotations

import logging

import httpx

from app.integrations.sources.base import RawEvent
from app.integrations.sources.util import parse_epoch_ms, strip_html

logger = logging.getLogger(__name__)


class SquarespaceEventsAdapter:
    """Adapter for a Squarespace events collection page."""

    name = "douglas_dsu"

    def __init__(
        self,
        page_url: str,
        *,
        campus: str = "Douglas",
        default_organizer: str = "Douglas Students' Union",
        site_origin: str | None = None,
        include_past: bool = True,
    ) -> None:
        self._page_url = page_url
        self._campus = campus
        self._default_organizer = default_organizer
        # Squarespace splits events into upcoming/past; include both for volume.
        self._include_past = include_past
        # Origin used to absolutise relative fullUrl values.
        self._origin = site_origin or _origin_of(page_url)

    async def fetch(self, limit: int) -> list[RawEvent]:
        """Fetch upcoming events from the Squarespace JSON view."""

        logger.debug("SquarespaceEventsAdapter fetching %s", self._page_url)
        try:
            async with httpx.AsyncClient(
                timeout=30.0, headers={"User-Agent": "ClubConcierge/0.1"}
            ) as client:
                response = await client.get(
                    self._page_url, params={"format": "json"}
                )
                response.raise_for_status()
                payload = response.json()
        except Exception:
            logger.error("DSU events fetch failed", exc_info=True)
            raise

        items = list(payload.get("upcoming") or [])
        if self._include_past:
            items.extend(payload.get("past") or [])
        events: list[RawEvent] = [self._to_raw_event(it) for it in items[:limit]]
        logger.debug("SquarespaceEventsAdapter parsed %d events", len(events))
        return events

    def _to_raw_event(self, item: dict[str, object]) -> RawEvent:
        loc = item.get("location")
        location = None
        if isinstance(loc, dict):
            parts = [
                loc.get("addressTitle"),
                loc.get("addressLine1"),
                loc.get("addressLine2"),
            ]
            location = ", ".join(str(p) for p in parts if p) or None

        full_url = item.get("fullUrl")
        url = None
        if isinstance(full_url, str):
            url = full_url if full_url.startswith("http") else self._origin + full_url

        return RawEvent(
            source=self.name,
            external_id=str(item.get("id") or item.get("urlId") or full_url),
            title=strip_html(_as_str(item.get("title"))) or "Untitled Event",
            url=url,
            organizer=self._default_organizer,
            location=location,
            campus=self._campus,
            start=parse_epoch_ms(item.get("startDate")),
            end=parse_epoch_ms(item.get("endDate")),
            cost_text=None,
            description=strip_html(_as_str(item.get("excerpt"))),
        )


def _origin_of(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
