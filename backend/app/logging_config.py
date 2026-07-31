"""Structured logging configuration.

Every async I/O wrapper in the codebase obtains its logger via
``logging.getLogger(__name__)`` and logs at the I/O boundary (DEBUG on
entry/exit, ERROR with ``exc_info`` on failure), per the project conventions.
This module installs a single consistent handler/formatter for the whole
process. It is idempotent: calling :func:`configure_logging` more than once
will not attach duplicate handlers.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED: bool = False

_LOG_FORMAT: str = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
_DATE_FORMAT: str = "%Y-%m-%dT%H:%M:%S%z"


def configure_logging(level: str = "INFO") -> None:
    """Install a stdout stream handler with a structured formatter.

    Args:
        level: Root log level name (e.g. ``"DEBUG"``, ``"INFO"``). Unknown
            names fall back to ``INFO``.
    """

    global _CONFIGURED

    resolved_level = logging.getLevelName(level.upper())
    if not isinstance(resolved_level, int):
        resolved_level = logging.INFO

    root = logging.getLogger()
    root.setLevel(resolved_level)

    if _CONFIGURED:
        # Already installed; just adjust the level and return.
        return

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root.addHandler(handler)

    _CONFIGURED = True
