"""Stage 01 ingestion: scrape -> dedup -> free-filter -> embed -> commit.

Submodules are imported directly (e.g. ``from app.ingestion.pipeline import
IngestionPipeline``) to avoid import cycles with ``app.integrations``.
"""

from __future__ import annotations
