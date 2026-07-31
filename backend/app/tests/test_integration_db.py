"""Live integration tests for the asyncpg repository layer.

These exercise every repository against a real Postgres + pgvector database and
auto-skip (via the ``db_pool`` fixture) when ``DATABASE_URL`` is unreachable.
Each test cleans up the rows it creates so the suite is idempotent.

Run after starting the local stack:

    supabase start
    .venv/Scripts/python -m pytest app/tests/test_integration_db.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from app.db import (
    EventsRepository,
    HashesRepository,
    ProfilesRepository,
    TokensRepository,
)
from app.models import EventRecord, ProcessedHash, StudentProfile, UserToken

pytestmark = pytest.mark.asyncio


def _vector(value: float, dim: int = 1536) -> list[float]:
    """Build a constant 1536-dim test embedding."""

    return [value] * dim


async def test_event_insert_get_and_dedup(db_pool: asyncpg.Pool) -> None:
    repo = EventsRepository(db_pool)
    image_hash = f"sha256-{uuid.uuid4().hex}"
    event = EventRecord(
        title="CS Industry Networking Mixer",
        organizer="CSSS",
        location="AMS Nest",
        campus="UBC",
        event_timestamp=datetime(2026, 7, 2, 18, 0, tzinfo=timezone.utc),
        original_image_url="https://cdn.example/flyer.jpg",
        image_hash=image_hash,
        has_free_food=True,
        perks=["free_food", "networking"],
        embedding=_vector(0.01),
    )
    saved = await repo.insert_event(event)
    try:
        assert saved.id is not None
        assert saved.created_at is not None
        assert saved.perks == ["free_food", "networking"]

        fetched = await repo.get_by_id(saved.id)
        assert fetched is not None
        assert fetched.title == event.title
        assert fetched.embedding is not None
        assert len(fetched.embedding) == 1536

        assert await repo.image_hash_exists(image_hash) is True
        assert await repo.image_hash_exists("sha256-does-not-exist") is False
    finally:
        assert saved.id is not None
        await repo.delete_by_id(saved.id)


async def test_semantic_search_respects_campus_filter(db_pool: asyncpg.Pool) -> None:
    repo = EventsRepository(db_pool)
    base_time = datetime(2026, 7, 4, 14, 0, tzinfo=timezone.utc)

    ubc = await repo.insert_event(
        EventRecord(
            title="UBC Free Pizza Hack Night",
            campus="UBC",
            event_timestamp=base_time,
            image_hash=f"sha256-{uuid.uuid4().hex}",
            has_free_food=True,
            perks=["free_food"],
            embedding=_vector(0.02),
        )
    )
    douglas = await repo.insert_event(
        EventRecord(
            title="Douglas Career Fair",
            campus="Douglas",
            event_timestamp=base_time,
            image_hash=f"sha256-{uuid.uuid4().hex}",
            has_free_food=True,
            perks=["free_food"],
            embedding=_vector(0.02),
        )
    )
    try:
        results = await repo.semantic_search(
            _vector(0.02),
            limit=10,
            campus="UBC",
            require_free_food=True,
            required_perks=["free_food"],
        )
        ids = {r.id for r in results}
        assert ubc.id in ids
        # Campus boundary must exclude the Douglas event.
        assert douglas.id not in ids
        for r in results:
            # Campus boundary is the invariant under test.
            assert r.campus == "UBC"
            # Cosine similarity is mathematically in [-1, 1].
            assert -1.0001 <= r.similarity <= 1.0001
    finally:
        assert ubc.id is not None and douglas.id is not None
        await repo.delete_by_id(ubc.id)
        await repo.delete_by_id(douglas.id)


async def test_hashes_two_stage_dedup(db_pool: asyncpg.Pool) -> None:
    repo = HashesRepository(db_pool)
    md5 = f"md5-{uuid.uuid4().hex}"
    sha = f"sha-{uuid.uuid4().hex}"

    assert await repo.url_seen(md5) is False
    recorded = await repo.record(ProcessedHash(md5_url=md5, sha256_binary=sha))
    try:
        assert recorded.id is not None
        assert await repo.url_seen(md5) is True
        assert await repo.binary_seen(sha) is True
        # Idempotent upsert on the same URL must not raise.
        again = await repo.record(ProcessedHash(md5_url=md5, sha256_binary=sha))
        assert again.md5_url == md5
    finally:
        await db_pool.execute(
            "delete from public.processed_hashes where md5_url = $1", md5
        )


async def test_profile_upsert_roundtrip(db_pool: asyncpg.Pool) -> None:
    # user_profiles.id references auth.users; create a throwaway auth user.
    user_id = uuid.uuid4()
    await db_pool.execute(
        "insert into auth.users (id, instance_id, aud, role) "
        "values ($1, '00000000-0000-0000-0000-000000000000', 'authenticated', "
        "'authenticated')",
        user_id,
    )
    repo = ProfilesRepository(db_pool)
    try:
        saved = await repo.upsert(
            StudentProfile(
                id=user_id,
                campus="Douglas",
                program="CIS",
                interest_tags=["career"],
                transit_cutoff_minutes=1005,
            )
        )
        assert saved.created_at is not None

        updated = await repo.upsert(
            StudentProfile(
                id=user_id,
                campus="Douglas",
                program="Business",
                interest_tags=["career", "finance"],
                transit_cutoff_minutes=990,
            )
        )
        assert updated.program == "Business"
        assert updated.transit_cutoff_minutes == 990

        fetched = await repo.get(user_id)
        assert fetched is not None
        assert fetched.interest_tags == ["career", "finance"]
    finally:
        await repo.delete(user_id)
        await db_pool.execute("delete from auth.users where id = $1", user_id)


async def test_tokens_upsert_and_revoke(db_pool: asyncpg.Pool) -> None:
    user_id = uuid.uuid4()
    await db_pool.execute(
        "insert into auth.users (id, instance_id, aud, role) "
        "values ($1, '00000000-0000-0000-0000-000000000000', 'authenticated', "
        "'authenticated')",
        user_id,
    )
    repo = TokensRepository(db_pool)
    try:
        saved = await repo.upsert(
            UserToken(
                user_id=user_id,
                provider="google",
                access_token="access-1",
                refresh_token="refresh-1",
                scope="calendar.events",
                token_type="Bearer",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        assert saved.id is not None

        refreshed = await repo.upsert(
            UserToken(
                user_id=user_id,
                provider="google",
                access_token="access-2",
            )
        )
        # New access token applied; prior refresh token preserved via coalesce.
        assert refreshed.access_token == "access-2"
        assert refreshed.refresh_token == "refresh-1"

        fetched = await repo.get(user_id, "google")
        assert fetched is not None and fetched.access_token == "access-2"

        assert await repo.delete(user_id, "google") is True
        assert await repo.get(user_id, "google") is None
    finally:
        await db_pool.execute("delete from auth.users where id = $1", user_id)
