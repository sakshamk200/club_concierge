"""Deduplication ledger repository.

Backs the Stage 01 two-stage cryptographic dedup: a fast MD5-of-URL check
before downloading the image binary, and a SHA-256-of-binary check before any
Vision-LLM call. Both digests are recorded in ``public.processed_hashes``.
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg

from app.db.base import BaseRepository
from app.models.hash import ProcessedHash

logger = logging.getLogger(__name__)

_COLUMNS = "id, md5_url, sha256_binary, source_url, processed_at"


class HashesRepository(BaseRepository):
    """Data access for ``public.processed_hashes``."""

    async def url_seen(self, md5_url: str) -> bool:
        """First-stage check: has this image URL's MD5 been processed before?"""

        query = (
            "select exists(select 1 from public.processed_hashes "
            "where md5_url = $1)"
        )
        return bool(await self._fetchval(query, md5_url))

    async def binary_seen(self, sha256_binary: str) -> bool:
        """Second-stage check: has this image binary's SHA-256 been seen?"""

        query = (
            "select exists(select 1 from public.processed_hashes "
            "where sha256_binary = $1)"
        )
        return bool(await self._fetchval(query, sha256_binary))

    async def record(self, entry: ProcessedHash) -> ProcessedHash:
        """Insert a dedup entry.

        Uses ``on conflict (md5_url) do update`` so a re-seen URL upgrades its
        stored binary hash / provenance instead of raising a unique violation.
        """

        query = f"""
            insert into public.processed_hashes (md5_url, sha256_binary, source_url)
            values ($1, $2, $3)
            on conflict (md5_url) do update
                set sha256_binary = coalesce(
                        excluded.sha256_binary, public.processed_hashes.sha256_binary
                    ),
                    source_url = coalesce(
                        excluded.source_url, public.processed_hashes.source_url
                    )
            returning {_COLUMNS}
        """
        row = await self._fetchrow(
            query, entry.md5_url, entry.sha256_binary, entry.source_url
        )
        assert row is not None
        return _row_to_hash(row)


def _row_to_hash(row: asyncpg.Record) -> ProcessedHash:
    """Map a database row to a :class:`ProcessedHash`."""

    return ProcessedHash.model_validate(dict(row))
