"""Unit tests for the Pydantic data contracts (no database required)."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.models import (
    EventRecord,
    EventSearchResult,
    ProcessedHash,
    StudentProfile,
    UserToken,
)


def test_event_requires_title() -> None:
    with pytest.raises(ValidationError):
        EventRecord(title="")


def test_event_defaults() -> None:
    event = EventRecord(title="Career Panel")
    assert event.has_free_food is False
    assert event.perks == []
    assert event.embedding is None
    assert event.id is None


def test_event_search_result_carries_similarity() -> None:
    result = EventSearchResult(title="Mixer", similarity=0.87)
    assert result.similarity == pytest.approx(0.87)
    assert isinstance(result, EventRecord)


def test_student_profile_transit_cutoff() -> None:
    profile = StudentProfile(
        id=uuid.uuid4(),
        campus="Douglas",
        interest_tags=["career", "business"],
        transit_cutoff_minutes=1005,
    )
    assert profile.transit_cutoff_minutes == 1005
    assert "career" in profile.interest_tags


def test_user_token_provider_is_constrained() -> None:
    with pytest.raises(ValidationError):
        UserToken(user_id=uuid.uuid4(), provider="dropbox", access_token="x")  # type: ignore[arg-type]


def test_processed_hash_minimal() -> None:
    entry = ProcessedHash(md5_url="d41d8cd98f00b204e9800998ecf8427e")
    assert entry.sha256_binary is None
    assert entry.id is None
