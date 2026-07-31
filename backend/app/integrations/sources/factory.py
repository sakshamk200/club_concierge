"""Source adapter selection."""

from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.integrations.sources.base import SourceAdapter
from app.integrations.sources.livewhale import LiveWhaleAdapter
from app.integrations.sources.mock_source import MockSourceAdapter
from app.integrations.sources.squarespace_events import SquarespaceEventsAdapter
from app.integrations.sources.the_events_calendar import TheEventsCalendarAdapter

logger = logging.getLogger(__name__)


def get_sources(settings: Settings | None = None) -> list[SourceAdapter]:
    """Return the configured list of source adapters.

    Live website adapters (UBC AMS + Douglas DSU) when web scraping is enabled,
    otherwise the offline mock adapter.
    """

    settings = settings or get_settings()

    if settings.use_mock_sources or not settings.enable_web_scraping:
        logger.debug("Using MockSourceAdapter only")
        return [MockSourceAdapter()]

    sources: list[SourceAdapter] = [
        # Official campus event sources — one per school.
        TheEventsCalendarAdapter(
            settings.ams_events_api, name="ubc_ams", campus="UBC",
            default_organizer="AMS UBC",
        ),
        SquarespaceEventsAdapter(
            settings.dsu_events_url, campus="Douglas", include_past=False
        ),
        TheEventsCalendarAdapter(
            settings.bcitsa_events_api, name="bcit_sa", campus="BCIT",
            default_organizer="BCIT Student Association",
        ),
        LiveWhaleAdapter(settings.sfu_events_feed, name="sfu_livewhale", campus="SFU"),
    ]

    # Instagram activates automatically once an Apify token is configured.
    from app.integrations.sources.instagram import maybe_instagram_adapter

    instagram = maybe_instagram_adapter(settings)
    if instagram is not None:
        sources.append(instagram)

    logger.debug("Using live sources: %s", [s.name for s in sources])
    return sources
