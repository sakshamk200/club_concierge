"""Unit tests for the ingestion stage (offline; no DB or network)."""

from __future__ import annotations

import pytest

from app.ingestion import dedup
from app.integrations.sources.base import classify_free
from app.integrations.sources.mock_source import MockSourceAdapter


def test_classify_free_empty_cost_is_free() -> None:
    is_free, food = classify_free("", "Trivia Night", "Come play trivia")
    assert is_free is True
    assert food is False


def test_classify_free_detects_price() -> None:
    is_free, _ = classify_free("$15", "Gala Dinner", "Three course meal")
    assert is_free is False


def test_classify_free_detects_food_and_free_text() -> None:
    is_free, food = classify_free(None, "Study Jam", "Free pizza for everyone!")
    assert is_free is True
    assert food is True


@pytest.mark.asyncio
async def test_mock_source_adapter_returns_structured_events() -> None:
    events = await MockSourceAdapter().fetch(10)
    assert len(events) == 4
    assert all(e.title and e.campus in {"UBC", "Douglas"} for e in events)
    assert all(not e.needs_vision for e in events)


def test_md5_url_is_deterministic() -> None:
    a = dedup.md5_url("https://cdn/x.jpg")
    b = dedup.md5_url("https://cdn/x.jpg")
    c = dedup.md5_url("https://cdn/y.jpg")
    assert a == b
    assert a != c
    assert len(a) == 32


def test_sha256_binary_is_deterministic() -> None:
    a = dedup.sha256_binary(b"hello")
    b = dedup.sha256_binary(b"hello")
    c = dedup.sha256_binary(b"world")
    assert a == b
    assert a != c
    assert len(a) == 64
