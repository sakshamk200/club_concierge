"""Parsing helpers shared by source adapters."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(value: str | None) -> str | None:
    """Remove HTML tags and unescape entities from a rich-text field."""

    if not value:
        return None
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    return text or None


def parse_naive_utc(value: str | None) -> datetime | None:
    """Parse 'YYYY-MM-DD HH:MM:SS' (assumed UTC) into a tz-aware datetime."""

    if not value:
        return None
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc)


def parse_iso_date(value: str | None) -> datetime | None:
    """Parse an ISO date or datetime string into a tz-aware UTC datetime.

    Handles 'YYYY-MM-DD', full ISO datetimes, and trailing 'Z'.
    """

    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_epoch_ms(value: object) -> datetime | None:
    """Parse an epoch-milliseconds integer into a tz-aware UTC datetime."""

    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
