"""OAuth tokens repository.

Backs ``public.user_tokens``. The Stage 03 calendar tool node reads the owning
user's credential here before calling Google Calendar ``events.insert()`` or
Microsoft Graph ``POST /me/events``. Rows are unique per (user, provider).
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg

from app.db.base import BaseRepository
from app.models.token import CalendarProvider, UserToken

logger = logging.getLogger(__name__)

_COLUMNS = (
    "id, user_id, provider, access_token, refresh_token, scope, token_type, "
    "expires_at, created_at, updated_at"
)


class TokensRepository(BaseRepository):
    """Data access for ``public.user_tokens``."""

    async def get(
        self, user_id: UUID, provider: CalendarProvider
    ) -> UserToken | None:
        """Fetch the stored token for a (user, provider) pair, or ``None``."""

        query = (
            f"select {_COLUMNS} from public.user_tokens "
            "where user_id = $1 and provider = $2"
        )
        row = await self._fetchrow(query, user_id, provider)
        return _row_to_token(row) if row is not None else None

    async def upsert(self, token: UserToken) -> UserToken:
        """Insert or refresh a credential, keyed by (user_id, provider)."""

        query = f"""
            insert into public.user_tokens (
                user_id, provider, access_token, refresh_token, scope,
                token_type, expires_at
            )
            values ($1, $2, $3, $4, $5, $6, $7)
            on conflict (user_id, provider) do update
                set access_token = excluded.access_token,
                    refresh_token = coalesce(
                        excluded.refresh_token, public.user_tokens.refresh_token
                    ),
                    scope = excluded.scope,
                    token_type = excluded.token_type,
                    expires_at = excluded.expires_at
            returning {_COLUMNS}
        """
        row = await self._fetchrow(
            query,
            token.user_id,
            token.provider,
            token.access_token,
            token.refresh_token,
            token.scope,
            token.token_type,
            token.expires_at,
        )
        assert row is not None
        return _row_to_token(row)

    async def delete(self, user_id: UUID, provider: CalendarProvider) -> bool:
        """Revoke/remove a stored credential; True if a row was removed."""

        status = await self._execute(
            "delete from public.user_tokens where user_id = $1 and provider = $2",
            user_id,
            provider,
        )
        return status.endswith("1")


def _row_to_token(row: asyncpg.Record) -> UserToken:
    """Map a database row to a :class:`UserToken`."""

    return UserToken.model_validate(dict(row))
