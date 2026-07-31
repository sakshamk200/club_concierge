"""Student profiles repository.

Backs ``public.user_profiles`` — the preference store that drives Profile A
(UBC) versus Profile B (Douglas College) filtering behaviour.
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg

from app.db.base import BaseRepository
from app.models.profile import StudentProfile

logger = logging.getLogger(__name__)

_COLUMNS = (
    "id, campus, program, interest_tags, transit_cutoff_minutes, created_at"
)


class ProfilesRepository(BaseRepository):
    """Data access for ``public.user_profiles``."""

    async def get(self, user_id: UUID) -> StudentProfile | None:
        """Fetch a profile by user id, or ``None`` if it does not exist."""

        query = f"select {_COLUMNS} from public.user_profiles where id = $1"
        row = await self._fetchrow(query, user_id)
        return _row_to_profile(row) if row is not None else None

    async def upsert(self, profile: StudentProfile) -> StudentProfile:
        """Insert or update a profile keyed by ``id``.

        Returns the persisted row (with ``created_at`` populated).
        """

        query = f"""
            insert into public.user_profiles (
                id, campus, program, interest_tags, transit_cutoff_minutes
            )
            values ($1, $2, $3, $4, $5)
            on conflict (id) do update
                set campus = excluded.campus,
                    program = excluded.program,
                    interest_tags = excluded.interest_tags,
                    transit_cutoff_minutes = excluded.transit_cutoff_minutes
            returning {_COLUMNS}
        """
        row = await self._fetchrow(
            query,
            profile.id,
            profile.campus,
            profile.program,
            profile.interest_tags,
            profile.transit_cutoff_minutes,
        )
        assert row is not None
        return _row_to_profile(row)

    async def delete(self, user_id: UUID) -> bool:
        """Delete a profile; return True if a row was removed."""

        status = await self._execute(
            "delete from public.user_profiles where id = $1", user_id
        )
        return status.endswith("1")


def _row_to_profile(row: asyncpg.Record) -> StudentProfile:
    """Map a database row to a :class:`StudentProfile`."""

    return StudentProfile.model_validate(dict(row))
