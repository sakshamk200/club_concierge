"""Deduplication ledger data contract.

Mirrors ``public.processed_hashes``. Records the two-stage cryptographic
digests (MD5 of the image URL, SHA-256 of the fetched binary) used by the
Stage 01 ingestion worker to avoid resubmitting duplicate flyers to the
Vision-LLM API.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProcessedHash(BaseModel):
    """A recorded dedup entry for one processed flyer image."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = Field(default=None)
    md5_url: str = Field(description="First-stage MD5 digest of the image CDN URL.")
    sha256_binary: str | None = Field(
        default=None,
        description="Second-stage SHA-256 digest of the fetched image bytes.",
    )
    source_url: str | None = Field(default=None)
    processed_at: datetime | None = Field(default=None)
