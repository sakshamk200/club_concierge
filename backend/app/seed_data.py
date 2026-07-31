"""Sample event catalogue for the demo.

A curated set of UBC and Douglas College events used to populate the database
via the ``/admin/seed`` endpoint so the chat/search demo has realistic content.
These stand in for the records the Stage 01 ingestion pipeline would extract
from Instagram flyers in production.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.event import EventRecord


def _at(days: int, hour: int, minute: int = 0) -> datetime:
    """Build a timezone-aware timestamp ``days`` from now at a wall-clock time."""

    base = datetime.now(timezone.utc) + timedelta(days=days)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def sample_events() -> list[EventRecord]:
    """Return the demo event catalogue (embeddings filled in at seed time)."""

    return [
        EventRecord(
            title="CS Industry Networking Mixer",
            organizer="UBC Computer Science Student Society",
            location="AMS Student Nest, Room 2310",
            campus="UBC",
            event_timestamp=_at(2, 18, 0),
            has_free_food=True,
            perks=["free_food", "networking"],
            image_hash="seed-ubc-cs-mixer",
        ),
        EventRecord(
            title="Free Pizza Hack Night",
            organizer="nwPlus",
            location="ICICS X-wing",
            campus="UBC",
            event_timestamp=_at(1, 19, 0),
            has_free_food=True,
            perks=["free_food", "coding"],
            image_hash="seed-ubc-hack-night",
        ),
        EventRecord(
            title="Indie Live Music Night",
            organizer="UBC Music Club",
            location="The Nest Great Hall",
            campus="UBC",
            event_timestamp=_at(3, 20, 0),
            has_free_food=False,
            perks=["music", "social"],
            image_hash="seed-ubc-music",
        ),
        EventRecord(
            title="Intramural Soccer Kickoff",
            organizer="UBC Recreation",
            location="MacInnes Field",
            campus="UBC",
            event_timestamp=_at(4, 16, 0),
            has_free_food=False,
            perks=["sports", "fitness"],
            image_hash="seed-ubc-soccer",
        ),
        EventRecord(
            title="Business & CIS Career Fair",
            organizer="Douglas Students' Union",
            location="New Westminster Campus, Concourse",
            campus="Douglas",
            event_timestamp=_at(2, 11, 0),
            has_free_food=True,
            perks=["free_food", "career", "networking"],
            image_hash="seed-dc-career-fair",
        ),
        EventRecord(
            title="Resume & Interview Workshop",
            organizer="Douglas Career Centre",
            location="New Westminster Campus, Room 4920",
            campus="Douglas",
            event_timestamp=_at(1, 13, 30),
            has_free_food=False,
            perks=["career", "workshop"],
            image_hash="seed-dc-resume",
        ),
        EventRecord(
            title="Free Lunch & Study Jam",
            organizer="Douglas Peer Tutoring",
            location="Coquitlam Campus, Library Commons",
            campus="Douglas",
            event_timestamp=_at(3, 12, 0),
            has_free_food=True,
            perks=["free_food", "study"],
            image_hash="seed-dc-study-jam",
        ),
        EventRecord(
            title="Intro to Data Science Workshop",
            organizer="Douglas CIS Club",
            location="New Westminster Campus, Room 2710",
            campus="Douglas",
            event_timestamp=_at(5, 14, 0),
            has_free_food=False,
            perks=["workshop", "computing"],
            image_hash="seed-dc-data-science",
        ),
    ]
