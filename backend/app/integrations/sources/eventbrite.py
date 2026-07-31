"""Eventbrite adapter — regional free community events.

Scrapes Eventbrite's public free-events listing for a location and parses the
embedded schema.org JSON-LD ``ItemList`` of events. Provides upcoming, varied,
real free events near each campus (Vancouver for UBC, New Westminster for
Douglas) to complement the on-campus sources.
"""

from __future__ import annotations

import json
import logging
import re

import httpx

from app.integrations.sources.base import RawEvent
from app.integrations.sources.util import parse_iso_date, strip_html

logger = logging.getLogger(__name__)

_LDJSON_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.S
)


class EventbriteAdapter:
    """Adapter for an Eventbrite location free-events listing page."""

    def __init__(
        self,
        listing_url: str,
        *,
        name: str,
        campus: str,
        area_label: str,
    ) -> None:
        self.name = name
        self._listing_url = listing_url
        self._campus = campus
        self._area_label = area_label

    async def fetch(self, limit: int) -> list[RawEvent]:
        logger.debug("EventbriteAdapter fetching %s", self._listing_url)
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "Mozilla/5.0 (ClubConcierge)"},
                follow_redirects=True,
            ) as client:
                response = await client.get(self._listing_url)
                response.raise_for_status()
                html = response.text
        except Exception:
            logger.error("Eventbrite fetch failed", exc_info=True)
            raise

        events = [self._to_raw_event(e) for e in _extract_events(html)[:limit]]
        logger.debug("EventbriteAdapter parsed %d events", len(events))
        return events

    def _to_raw_event(self, e: dict[str, object]) -> RawEvent:
        loc = e.get("location") or {}
        location = None
        if isinstance(loc, dict):
            addr = loc.get("address") or {}
            locality = addr.get("addressLocality") if isinstance(addr, dict) else None
            parts = [loc.get("name"), locality]
            location = ", ".join(str(p) for p in parts if p) or None

        url = e.get("url") if isinstance(e.get("url"), str) else None
        return RawEvent(
            source=self.name,
            external_id=str(url or e.get("name")),
            title=strip_html(str(e.get("name", ""))) or "Untitled Event",
            url=url,
            organizer=f"Eventbrite · {self._area_label}",
            location=location,
            campus=self._campus,
            start=parse_iso_date(_as_str(e.get("startDate"))),
            end=parse_iso_date(_as_str(e.get("endDate"))),
            cost_text=_extract_cost(e.get("offers")),
            description=strip_html(_as_str(e.get("description"))),
            image_url=_as_str(e.get("image")),
        )


def _extract_events(html: str) -> list[dict[str, object]]:
    """Pull Event objects out of the page's JSON-LD blocks."""

    events: list[dict[str, object]] = []
    for block in _LDJSON_RE.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for node in data if isinstance(data, list) else [data]:
            if not isinstance(node, dict):
                continue
            if node.get("@type") == "Event":
                events.append(node)
            elif node.get("@type") == "ItemList":
                for entry in node.get("itemListElement", []):
                    item = entry.get("item") if isinstance(entry, dict) else None
                    if isinstance(item, dict) and item.get("@type") == "Event":
                        events.append(item)
    return events


def _extract_cost(offers: object) -> str | None:
    """Derive a cost string from a JSON-LD offers object/list.

    Returns 'free' for zero/absent prices, otherwise a '$X' string.
    """

    if not offers:
        return "free"
    offer = offers[0] if isinstance(offers, list) and offers else offers
    if not isinstance(offer, dict):
        return "free"
    price = offer.get("price") or offer.get("lowPrice")
    if price in (None, "", "0", "0.0", "0.00", 0):
        return "free"
    try:
        return "free" if float(price) == 0 else f"${price}"
    except (TypeError, ValueError):
        return None


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
