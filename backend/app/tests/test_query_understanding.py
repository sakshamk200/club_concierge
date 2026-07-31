"""Unit tests for natural-language query understanding (offline)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.query_understanding import parse_intent

# A fixed reference instant: Wednesday, 2026-07-29 20:00 UTC (~1pm Pacific).
_NOW = datetime(2026, 7, 29, 20, 0, tzinfo=timezone.utc)


def test_detects_free_food_phrase() -> None:
    assert parse_intent("any free pizza today?", _NOW).require_free_food is True
    # Bare "food" must not over-trigger.
    assert parse_intent("food trucks festival", _NOW).require_free_food is False


def test_detects_campus_from_text() -> None:
    assert parse_intent("career fairs at SFU", _NOW).campus == "SFU"
    assert parse_intent("what's on at douglas", _NOW).campus == "Douglas"
    assert parse_intent("anything fun this week", _NOW).campus is None


def test_tomorrow_window_is_one_day() -> None:
    intent = parse_intent("events tomorrow", _NOW)
    assert intent.time_label == "tomorrow"
    assert intent.starts_after is not None and intent.starts_before is not None
    assert intent.starts_before > intent.starts_after
    # Window spans a single local day (< 25h to allow for the timezone offset).
    span = intent.starts_before - intent.starts_after
    assert span.total_seconds() < 25 * 3600


def test_weekend_window_spans_two_days() -> None:
    intent = parse_intent("free food this weekend", _NOW)
    assert intent.time_label == "this weekend"
    assert intent.require_free_food is True
    span = intent.starts_before - intent.starts_after
    assert 24 * 3600 < span.total_seconds() < 3 * 24 * 3600


def test_no_time_phrase_leaves_window_open() -> None:
    intent = parse_intent("coding workshops", _NOW)
    assert intent.starts_after is None
    assert intent.starts_before is None
    assert intent.time_label is None


def test_next_month_is_not_this_month() -> None:
    this_m = parse_intent("career fairs this month", _NOW)
    next_m = parse_intent("get a job next month", _NOW)
    assert this_m.time_label == "this month"
    assert next_m.time_label == "next month"
    # Next month's window must start after this month's window ends.
    assert next_m.starts_after > this_m.starts_before


def test_topic_detected_without_theme_word() -> None:
    assert parse_intent("i really want to get a job", _NOW).topic == "career"
    assert parse_intent("somewhere to meet new people", _NOW).topic == "social"
    assert parse_intent("random query", _NOW).topic is None
