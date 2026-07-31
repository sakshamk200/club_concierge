"""Service layer: embeddings, retrieval, and grounded answer composition."""

from __future__ import annotations

from app.services.embeddings import Embedder, get_embedder
from app.services.rag import compose_answer
from app.services.retrieval import RetrievalService

__all__ = ["Embedder", "get_embedder", "compose_answer", "RetrievalService"]
