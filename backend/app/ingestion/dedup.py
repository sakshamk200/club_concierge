"""Cryptographic digests for the two-stage deduplication.

Stage 1 hashes the image URL (cheap, pre-download). Stage 2 hashes the fetched
image binary (authoritative, catches reposts under different URLs). Pure
functions so they are trivially unit-testable.
"""

from __future__ import annotations

import hashlib


def md5_url(image_url: str) -> str:
    """Return the hex MD5 digest of an image URL (first-stage dedup key)."""

    return hashlib.md5(image_url.encode("utf-8")).hexdigest()


def sha256_binary(image_bytes: bytes) -> str:
    """Return the hex SHA-256 digest of image bytes (second-stage dedup key)."""

    return hashlib.sha256(image_bytes).hexdigest()
