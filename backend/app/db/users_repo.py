"""Application users repository.

Backs ``public.app_users`` — first-party accounts with hashed passwords and
profile preferences. Reached only through the backend service connection; the
table carries RLS with no public policies.
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg

from app.db.base import BaseRepository
from app.models.user import AppUser

logger = logging.getLogger(__name__)

_COLUMNS = (
    "id, email, name, password_hash, campus, program, interests, "
    "created_at, updated_at"
)


class UsersRepository(BaseRepository):
    """Data access for ``public.app_users``."""

    async def create(
        self, *, email: str, name: str, password_hash: str
    ) -> AppUser:
        """Insert a new account; raises asyncpg.UniqueViolationError if taken."""

        query = f"""
            insert into public.app_users (email, name, password_hash)
            values (lower($1), $2, $3)
            returning {_COLUMNS}
        """
        row = await self._fetchrow(query, email.strip(), name.strip(), password_hash)
        assert row is not None
        return _row_to_user(row)

    async def get_by_email(self, email: str) -> AppUser | None:
        """Fetch an account by email (case-insensitive)."""

        query = f"select {_COLUMNS} from public.app_users where email = lower($1)"
        row = await self._fetchrow(query, email.strip())
        return _row_to_user(row) if row is not None else None

    async def get_by_id(self, user_id: UUID) -> AppUser | None:
        """Fetch an account by primary key."""

        query = f"select {_COLUMNS} from public.app_users where id = $1"
        row = await self._fetchrow(query, user_id)
        return _row_to_user(row) if row is not None else None

    async def update_profile(
        self,
        user_id: UUID,
        *,
        name: str,
        campus: str | None,
        program: str | None,
        interests: list[str],
    ) -> AppUser | None:
        """Update editable profile fields; returns the fresh row."""

        query = f"""
            update public.app_users
               set name = $2, campus = $3, program = $4, interests = $5
             where id = $1
            returning {_COLUMNS}
        """
        row = await self._fetchrow(
            query, user_id, name.strip(), campus, program, interests
        )
        return _row_to_user(row) if row is not None else None


def _row_to_user(row: asyncpg.Record) -> AppUser:
    """Map a database row to an :class:`AppUser`."""

    return AppUser.model_validate(dict(row))
