"""Stage 01 ingestion pipeline orchestration (source-agnostic).

For each source adapter, the pipeline collects normalised RawEvents and runs:

    dedup (MD5 source-id) -> content hash (SHA-256) -> free filter ->
    validate -> embed -> atomic commit.

Every source adapter returns already-structured ``RawEvent`` records — website
feeds are structured natively, and the Instagram adapter reads flyer images
with a vision model internally before returning structured events. Duplicate,
non-free, or malformed events are skipped and counted rather than aborting the
run.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.db.events_repo import EventsRepository
from app.db.hashes_repo import HashesRepository
from app.ingestion import dedup
from app.integrations.sources.base import (
    CAMPUS_SOURCES,
    MIN_RELEVANCE,
    RawEvent,
    SourceAdapter,
    classify_free,
    infer_campus,
    is_campus_relevant,
    is_student_noise,
    relevance_score,
)
from app.integrations.sources.mock_source import MockSourceAdapter
from app.models.event import EventRecord
from app.models.hash import ProcessedHash
from app.services.embeddings import Embedder, build_event_embedding_text

logger = logging.getLogger(__name__)


@dataclass
class IngestionStats:
    """Outcome counters for one ingestion run."""

    scraped: int = 0
    skipped_not_free: int = 0
    duplicates: int = 0
    failed: int = 0
    inserted: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "scraped": self.scraped,
            "skipped_not_free": self.skipped_not_free,
            "duplicates": self.duplicates,
            "failed": self.failed,
            "inserted": self.inserted,
        }


class IngestionPipeline:
    """Coordinates multi-source scraping, dedup, free-filter, embed, persist."""

    def __init__(
        self,
        *,
        sources: list[SourceAdapter],
        embedder: Embedder,
        events_repo: EventsRepository,
        hashes_repo: HashesRepository,
        free_only: bool = True,
        per_source_limit: int = 40,
        fallback_to_mock: bool = True,
    ) -> None:
        self._sources = sources
        self._embedder = embedder
        self._events = events_repo
        self._hashes = hashes_repo
        self._free_only = free_only
        self._limit = per_source_limit
        self._fallback_to_mock = fallback_to_mock

    async def run(self) -> IngestionStats:
        """Run one ingestion pass across all configured sources."""

        stats = IngestionStats()
        raw_events = await self._collect()
        stats.scraped = len(raw_events)
        logger.info("Ingestion: %d events scraped from sources", stats.scraped)

        for raw in raw_events:
            try:
                if await self._process(raw, stats):
                    stats.inserted += 1
            except Exception:
                logger.error(
                    "Failed to process event %s/%s",
                    raw.source,
                    raw.external_id,
                    exc_info=True,
                )
                stats.failed += 1

        logger.info("Ingestion complete: %s", stats.as_dict())
        return stats

    async def _collect(self) -> list[RawEvent]:
        """Gather events from every source, tolerating per-source failures."""

        collected: list[RawEvent] = []
        for source in self._sources:
            try:
                events = await source.fetch(self._limit)
                logger.debug("Source %s returned %d events", source.name, len(events))
                collected.extend(events)
            except Exception:
                logger.error(
                    "Source %s failed; continuing", source.name, exc_info=True
                )

        # If every live source failed/empty, fall back to offline fixtures so a
        # demo still works without network.
        if not collected and self._fallback_to_mock:
            logger.warning("No live events; falling back to MockSourceAdapter")
            collected.extend(await MockSourceAdapter().fetch(self._limit))

        relevant: list[RawEvent] = []
        for e in collected:
            if not is_campus_relevant(e.source, e.title, e.description):
                continue
            # Administrative noise (thesis defences, senate, closures) is not
            # something a student attends — drop it outright.
            if is_student_noise(e.title, e.description):
                continue
            # Low-signal listings (lectures, notices) must clear a minimum
            # student-relevance score to enter the catalogue.
            if relevance_score(e.title, e.description) < MIN_RELEVANCE:
                continue
            # Trust on-campus sources' campus; infer it for third-party sources
            # from the event itself and drop anything not mappable to UBC/Douglas.
            if e.source not in CAMPUS_SOURCES:
                campus = infer_campus(e.title, e.description, e.location)
                if campus is None:
                    continue
                e.campus = campus
            relevant.append(e)
        logger.debug("campus relevance: %d -> %d", len(collected), len(relevant))
        return _balance_sources(_future_only(_collapse_recurring(relevant)))

    async def _process(self, raw: RawEvent, stats: IngestionStats) -> bool:
        """Process one RawEvent; return True if a new event was inserted."""

        # Stage 1 dedup: MD5 of the stable source identity.
        identity = f"{raw.source}:{raw.external_id}"
        url_hash = dedup.md5_url(identity)
        if await self._hashes.url_seen(url_hash):
            stats.duplicates += 1
            return False

        # Stage 2 dedup: SHA-256 of the event's canonical text.
        canonical = f"{raw.source}|{raw.title}|{raw.start}|{raw.location}"
        content_hash = dedup.sha256_binary(canonical.encode("utf-8"))
        if await self._hashes.binary_seen(content_hash):
            await self._record_hash(url_hash, content_hash, raw.url)
            stats.duplicates += 1
            return False

        # Free-event classification + filter.
        is_free, has_free_food = classify_free(
            raw.cost_text, raw.title, raw.description
        )
        if self._free_only and not is_free:
            stats.skipped_not_free += 1
            return False

        # Build the validated EventRecord.
        event = _raw_to_event(raw, has_free_food)
        event.original_image_url = raw.url
        event.image_hash = content_hash

        # Embed and persist.
        text = build_event_embedding_text(
            event.title, event.organizer, event.location, event.campus, event.perks
        )
        event.embedding = await self._embedder.embed_text(text)
        await self._events.insert_event(event)
        await self._record_hash(url_hash, content_hash, raw.url)
        logger.debug("Inserted '%s' from %s", event.title, raw.source)
        return True

    async def _record_hash(
        self, url_hash: str, content_hash: str, source_url: str | None
    ) -> None:
        await self._hashes.record(
            ProcessedHash(
                md5_url=url_hash, sha256_binary=content_hash, source_url=source_url
            )
        )


_DATE_IN_TITLE_RE = re.compile(
    r"\|?\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
    r"\d{1,2}(?:st|nd|rd|th)?,?\s*\d{0,4}",
    re.IGNORECASE,
)
_FORMAT_PREFIX_RE = re.compile(
    r"^(?:virtual live|virtual|e-?learning|online|in-person|hybrid|"
    r"downtown campus|burnaby campus|[a-z ]*campus)\s*\|\s*",
    re.IGNORECASE,
)
# Parenthetical clock-time fragments baked into titles, e.g. "(9:30 - 12:30)".
_TIME_PAREN_RE = re.compile(r"\([^)]*\d{1,2}:\d{2}[^)]*\)?")
# Leading article, for dedup-key normalisation ("The Legacy Ball" -> "legacy ball").
_LEADING_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)


def _normalize_title(title: str) -> str:
    """Normalise a title for de-duplication.

    Strips dates baked into titles (e.g. "Resume Walk-In | June 30, 2026") and
    leading format/location prefixes (e.g. "Virtual Live | ...") so recurring
    series collapse to a single entry.
    """

    text = _DATE_IN_TITLE_RE.sub("", title)
    text = _FORMAT_PREFIX_RE.sub("", text)
    text = _TIME_PAREN_RE.sub("", text)
    text = text.replace("|", " ")
    text = " ".join(text.split()).strip().lower()
    # Drop a leading article and trailing punctuation so "The Legacy Ball" and
    # "Legacy Ball!" collapse to one.
    text = _LEADING_ARTICLE_RE.sub("", text).strip(" .!-–—")
    return text or title.strip().lower()


_PER_SOURCE_CAP = 40


def _balance_sources(events: list[RawEvent]) -> list[RawEvent]:
    """Rank by student relevance and cap per source so no feed floods the rest.

    Within each source, the most student-relevant events (career fairs, socials,
    free-food nights) are kept ahead of low-signal listings.
    """

    by_source: dict[str, list[RawEvent]] = {}
    for event in events:
        by_source.setdefault(event.source, []).append(event)

    balanced: list[RawEvent] = []
    for source, group in by_source.items():
        group.sort(
            key=lambda e: relevance_score(e.title, e.description), reverse=True
        )
        kept = group[:_PER_SOURCE_CAP]
        if len(group) > len(kept):
            logger.debug("source %s capped: %d -> %d", source, len(group), len(kept))
        balanced.extend(kept)
    return balanced


_MAX_DAYS_AHEAD = 270


def _future_only(events: list[RawEvent]) -> list[RawEvent]:
    """Keep events in the near future — not past, not most of a year away."""

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=_MAX_DAYS_AHEAD)
    kept = [
        e for e in events
        if e.start is None or (now <= e.start <= horizon)
    ]
    logger.debug("time-window filter: %d -> %d", len(events), len(kept))
    return kept


def _collapse_recurring(events: list[RawEvent]) -> list[RawEvent]:
    """Collapse duplicate-titled events to a single earliest instance.

    Deduplicates both recurring series (a weekly event expanded into dozens of
    identical-titled occurrences) and the same regional event surfaced by more
    than one source, so each distinct event appears exactly once.
    """

    best: dict[str, RawEvent] = {}
    for event in events:
        key = _normalize_title(event.title)
        current = best.get(key)
        if current is None:
            best[key] = event
            continue
        # Prefer the earliest dated instance.
        if event.start is not None and (
            current.start is None or event.start < current.start
        ):
            best[key] = event
    collapsed = list(best.values())
    logger.debug("collapse duplicates: %d -> %d", len(events), len(collapsed))
    return collapsed


def _clean_display_title(title: str) -> str:
    """Strip format/location prefixes and baked-in dates for a tidy card title."""

    text = _FORMAT_PREFIX_RE.sub("", title)
    text = _DATE_IN_TITLE_RE.sub("", text)
    text = _TIME_PAREN_RE.sub("", text)
    text = text.strip().strip("|").strip().rstrip("-–—·").strip()
    return text or title.strip()


def _raw_to_event(raw: RawEvent, has_free_food: bool) -> EventRecord:
    """Map a structured RawEvent to a validated EventRecord."""

    perks: list[str] = []
    if has_free_food:
        perks.append("free_food")
    return EventRecord(
        title=_clean_display_title(raw.title),
        organizer=raw.organizer,
        location=raw.location,
        campus=raw.campus,
        event_timestamp=raw.start,
        registration_deadline=None,
        original_image_url=raw.url,
        has_free_food=has_free_food,
        perks=perks,
    )
