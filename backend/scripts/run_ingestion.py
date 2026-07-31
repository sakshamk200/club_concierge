"""Run a single Stage 01 ingestion pass from the CLI.

Usage (from /backend):
    .venv/Scripts/python scripts/run_ingestion.py

Uses real providers when APIFY_API_TOKEN / OPENAI_API_KEY are set, otherwise the
offline mock scraper + Vision-LLM so it runs with no credentials.
"""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure the backend package root is importable when run as a script file.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.ingestion.worker import run_once
from app.logging_config import configure_logging


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    stats = asyncio.run(run_once())
    print("Ingestion run complete:")
    for key, value in stats.items():
        print(f"  {key:11} {value}")


if __name__ == "__main__":
    main()
