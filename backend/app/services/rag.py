"""Grounded answer composition.

Produces a conversational reply that is strictly grounded in the retrieved
event records — the hallucination-free constraint from the proposal. With no
LLM configured (demo default), this builds a deterministic, template-based
summary over the retrieved events so the chat experience works fully offline.
The phrasing mirrors what a constrained RAG prompt would return: it never
invents events and says so plainly when nothing matched.
"""

from __future__ import annotations

import logging

from app.models.event import EventSearchResult

logger = logging.getLogger(__name__)


def compose_answer(
    query: str,
    results: list[EventSearchResult],
    *,
    campus: str | None = None,
    require_free_food: bool = False,
) -> str:
    """Compose a grounded natural-language answer over retrieved events.

    Args:
        query: The student's original query (echoed for context).
        results: Retrieved, verified event records (already filtered/ranked).
        campus: Active campus scope, if any.
        require_free_food: Whether the free-food filter was active.

    Returns:
        A short conversational reply grounded only in ``results``.
    """

    scope_bits: list[str] = []
    if campus:
        scope_bits.append(f"at {campus}")
    if require_free_food:
        scope_bits.append("with free food")
    scope = (" " + " ".join(scope_bits)) if scope_bits else ""

    if not results:
        logger.debug("compose_answer: no grounding results")
        return (
            f"I couldn't find any verified events{scope} matching "
            f"“{query}”. Try a broader search or a different campus "
            "filter."
        )

    count = len(results)
    lead = (
        f"I found {count} verified event{'s' if count != 1 else ''}{scope} "
        f"matching “{query}”:"
    )

    lines: list[str] = [lead]
    for result in results:
        when = (
            result.event_timestamp.strftime("%a %b %d, %I:%M %p")
            if result.event_timestamp is not None
            else "time TBA"
        )
        where = result.location or "location TBA"
        org = f" — {result.organizer}" if result.organizer else ""
        perks = ""
        if result.has_free_food:
            perks = " \U0001f355 free food"
        lines.append(f"• {result.title}{org} | {when} @ {where}{perks}")

    return "\n".join(lines)
