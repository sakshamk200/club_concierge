"""Offline ingestion fixtures.

Deterministic sample "Instagram posts" used by the mock scraper, plus the
ground-truth structured extraction the mock Vision-LLM returns for each. These
stand in for the live Instagram → Apify → GPT-4o Vision path so the ingestion
pipeline runs end-to-end with no credentials. Each post carries inline image
bytes (derived from the caption) so the dedup + fetch stages exercise real
hashing logic without any network access.

These events are intentionally distinct from app.seed_data so an ingestion run
visibly adds *new* events to the catalogue during the demo.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.event import EventRecord


def _at(days: int, hour: int, minute: int = 0) -> datetime:
    base = datetime.now(timezone.utc) + timedelta(days=days)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


# Each entry: (handle, post_id, image_url, caption, extracted EventRecord).
# The EventRecord is what a Vision-LLM would return after reading the flyer.
_POSTS: list[dict[str, object]] = [
    {
        "handle": "ubccsss",
        "post_id": "ig_ubccsss_001",
        "image_url": "https://instagram.fyvr1-1.fna.fbcdn.net/v/ubccsss_techtalk.jpg",
        "caption": (
            "AI & Machine Learning Tech Talk \U0001f9e0 Free samosas! "
            "Thursday @ ICICS, all CS students welcome."
        ),
        "event": EventRecord(
            title="AI & Machine Learning Tech Talk",
            organizer="UBC Computer Science Student Society",
            location="ICICS/CS Building, Room 202",
            campus="UBC",
            event_timestamp=_at(2, 17, 30),
            has_free_food=True,
            perks=["free_food", "tech_talk", "networking"],
        ),
    },
    {
        "handle": "nwplus",
        "post_id": "ig_nwplus_002",
        "image_url": "https://instagram.fyvr1-1.fna.fbcdn.net/v/nwplus_designjam.jpg",
        "caption": (
            "Design Jam Workshop \U0001f3a8 Learn Figma in a night. "
            "Snacks provided. Nest Room 2306."
        ),
        "event": EventRecord(
            title="UX Design Jam Workshop",
            organizer="nwPlus",
            location="AMS Student Nest, Room 2306",
            campus="UBC",
            event_timestamp=_at(4, 18, 0),
            has_free_food=True,
            perks=["free_food", "workshop", "design"],
        ),
    },
    {
        "handle": "douglas_su",
        "post_id": "ig_douglassu_003",
        "image_url": "https://instagram.fyvr1-1.fna.fbcdn.net/v/douglassu_townhall.jpg",
        "caption": (
            "Students' Union Town Hall \U0001f4e2 Coquitlam Campus atrium. "
            "Bring your questions, coffee is on us."
        ),
        "event": EventRecord(
            title="Students' Union Town Hall",
            organizer="Douglas Students' Union",
            location="Coquitlam Campus, Atrium",
            campus="Douglas",
            event_timestamp=_at(3, 15, 0),
            has_free_food=True,
            perks=["free_food", "community"],
        ),
    },
    {
        "handle": "douglascareer",
        "post_id": "ig_douglascareer_004",
        "image_url": "https://instagram.fyvr1-1.fna.fbcdn.net/v/douglascareer_linkedin.jpg",
        "caption": (
            "LinkedIn Headshot & Networking Night \U0001f4bc New West Campus. "
            "Dress to impress. Register at the link."
        ),
        "event": EventRecord(
            title="LinkedIn Headshot & Networking Night",
            organizer="Douglas Career Centre",
            location="New Westminster Campus, Room 4900",
            campus="Douglas",
            event_timestamp=_at(5, 16, 30),
            registration_deadline=_at(5, 12, 0),
            has_free_food=False,
            perks=["career", "networking"],
        ),
    },
]


def fixture_posts() -> list[dict[str, object]]:
    """Return the raw fixture post dicts."""

    return _POSTS
