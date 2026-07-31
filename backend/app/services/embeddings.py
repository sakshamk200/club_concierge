"""Embedding service.

Produces 1536-dimensional vectors compatible with the ``events.embedding``
column via :class:`LocalHashingEmbedder` — a deterministic, dependency-free
hashing vectorizer behind the :class:`Embedder` protocol. It needs no API key
or network, so the app runs fully offline. Cosine similarity between vectors
reflects shared/related vocabulary, which is enough for semantic-style
retrieval; a small keyword expansion map bridges common query/event synonyms
(e.g. "food" ~ "pizza").
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Protocol

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Lightweight synonym/keyword expansion so the offline embedder bridges obvious
# query/event vocabulary gaps during the demo. Each token, when present, also
# contributes its expansion tokens to the vector.
_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "food": ("pizza", "snacks", "meal", "lunch", "dinner", "free"),
    "free": ("food", "pizza", "snacks", "complimentary"),
    "pizza": ("food", "free", "snacks"),
    "cs": ("computing", "computer", "science", "coding", "software"),
    "computing": ("cs", "computer", "science", "software"),
    "networking": ("mixer", "social", "career", "industry"),
    "career": ("job", "industry", "networking", "professional", "fair"),
    "job": ("career", "industry", "hiring", "fair"),
    "workshop": ("session", "hands", "training", "learn"),
    "study": ("academic", "learning", "tutoring"),
    "music": ("concert", "band", "live", "performance"),
    "sports": ("game", "fitness", "athletics", "intramural"),
}


def _tokenize(text: str) -> list[str]:
    """Lowercase-tokenize text into alphanumeric tokens (with expansions)."""

    tokens = _TOKEN_RE.findall(text.lower())
    expanded: list[str] = list(tokens)
    for token in tokens:
        expanded.extend(_EXPANSIONS.get(token, ()))
    return expanded


class Embedder(Protocol):
    """Common interface for embedding providers."""

    async def embed_text(self, text: str) -> list[float]:
        """Return the embedding vector for a single text."""

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for a list of texts."""


class LocalHashingEmbedder:
    """Deterministic, offline hashing vectorizer.

    Tokens are hashed into ``dim`` buckets with a signed contribution; the
    accumulated vector is L2-normalised so cosine similarity is well-defined.
    Pure-Python and dependency-free.
    """

    def __init__(self, dim: int = 1536) -> None:
        self._dim = dim

    def _embed_sync(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        for token in _tokenize(text):
            digest = hashlib.md5(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self._dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            # Empty/whitespace text → a tiny constant vector to stay non-null.
            return [1.0 / math.sqrt(self._dim)] * self._dim
        return [value / norm for value in vector]

    async def embed_text(self, text: str) -> list[float]:
        logger.debug("LocalHashingEmbedder.embed_text len=%d", len(text))
        return self._embed_sync(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        logger.debug("LocalHashingEmbedder.embed_batch n=%d", len(texts))
        return [self._embed_sync(text) for text in texts]


def get_embedder(settings: Settings | None = None) -> Embedder:
    """Return the embedder — the offline local hashing engine."""

    settings = settings or get_settings()
    logger.debug("Using LocalHashingEmbedder (deterministic, offline)")
    return LocalHashingEmbedder(dim=settings.embedding_dim)


def build_event_embedding_text(
    title: str,
    organizer: str | None,
    location: str | None,
    campus: str | None,
    perks: list[str],
) -> str:
    """Compose the canonical text used to embed an event record."""

    parts = [title]
    if organizer:
        parts.append(organizer)
    if location:
        parts.append(location)
    if campus:
        parts.append(campus)
    parts.extend(perks)
    return " ".join(parts)
