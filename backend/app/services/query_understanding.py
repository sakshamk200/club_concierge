"""Natural-language query understanding for the concierge.

Turns a free-text student query into structured retrieval filters so the AI
actually acts on what was asked. For example, "free pizza this weekend at SFU"
becomes ``campus=SFU``, ``require_free_food=True`` and a Saturday-Sunday time
window — instead of relying on the (weak) embedding alone.

Deterministic and dependency-free (regex + date math), so it is instant, free,
and safe to run on every request. Times are resolved in the campuses' local
zone (America/Vancouver) and returned as timezone-aware UTC bounds.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

_PACIFIC = ZoneInfo("America/Vancouver")

# Canonical relative time windows the model + rules may emit.
_TIME_LABELS = (
    "today",
    "tonight",
    "tomorrow",
    "this weekend",
    "this week",
    "next week",
    "this month",
    "next month",
)

# Coarse theme detection so retrieval can bias toward the right kind of event
# even when the phrasing never says the theme word (e.g. "get a job" -> career).
_TOPIC_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "career",
        (
            "job", "jobs", "career", "careers", "hiring", "resume", "cover letter",
            "interview", "internship", "intern ", "co-op", "coop", "networking",
            "linkedin", "recruit", "employment", "hired", "work experience",
        ),
    ),
    (
        "social",
        (
            "social", "party", "mixer", "meet people", "meet new", "make friends",
            "hangout", "hang out", "night out", "club night", "meetup",
        ),
    ),
    (
        "music",
        ("concert", "live music", "music", "band", "karaoke", "open mic", "dj"),
    ),
    (
        "sports",
        (
            "sport", "sports", "fitness", "gym", "yoga", "workout", "run ",
            "basketball", "soccer", "volleyball", "hike", "climbing",
        ),
    ),
    (
        "workshop",
        ("workshop", "seminar", "training", "skill", "learn to", "how to"),
    ),
    (
        "food",
        ("food", "lunch", "dinner", "snack", "pizza", "coffee", "bbq", "eat"),
    ),
)


def _detect_topic(q: str) -> str | None:
    """Map a query to a coarse theme (career, social, music, …) or None."""

    for topic, keywords in _TOPIC_KEYWORDS:
        if any(k in q for k in keywords):
            return topic
    return None

# Campus name/alias -> canonical campus label.
_CAMPUS_ALIASES: tuple[tuple[str, str], ...] = (
    ("douglas", "Douglas"),
    ("dsu", "Douglas"),
    ("ubc", "UBC"),
    ("sfu", "SFU"),
    ("simon fraser", "SFU"),
    ("bcit", "BCIT"),
)

# Phrases that clearly ask for free food (not bare "food"/"pizza", which are
# too broad and would over-trigger the filter).
_FREE_FOOD_PHRASES: tuple[str, ...] = (
    "free food",
    "free pizza",
    "free lunch",
    "free dinner",
    "free breakfast",
    "free snack",
    "free snacks",
    "free coffee",
    "free meal",
)


@dataclass
class QueryIntent:
    """Structured filters parsed from a natural-language query."""

    starts_after: datetime | None = None
    starts_before: datetime | None = None
    require_free_food: bool = False
    campus: str | None = None
    time_label: str | None = None
    topic: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "starts_after": self.starts_after.isoformat() if self.starts_after else None,
            "starts_before": self.starts_before.isoformat() if self.starts_before else None,
            "require_free_food": self.require_free_food,
            "campus": self.campus,
            "time_label": self.time_label,
            "topic": self.topic,
        }


# Cues that a query is a follow-up about the events already shown, rather than a
# fresh search (so we reuse the prior results instead of re-filtering to none).
_FOLLOWUP_CUES: tuple[str, ...] = (
    "which one",
    "which is",
    "the best",
    "best one",
    "choose one",
    "pick one",
    "just one",
    "only one",
    "choose",
    "recommend one",
    "narrow",
    "the first",
    "the second",
    "the third",
    "the last",
    "first one",
    "second one",
    "that one",
    "this one",
    "tell me more",
    "more info",
    "more details",
    "what about",
    "how about",
    "instead",
    "nah",
    "no wait",
)

_FOLLOWUP_PRONOUNS = ("it", "that", "this", "one", "them", "those", "these")


def is_followup(query: str) -> bool:
    """Heuristic: does this query refer back to already-shown events?"""

    q = query.lower().strip()
    if any(cue in q for cue in _FOLLOWUP_CUES):
        return True
    words = q.split()
    if len(words) <= 3 and any(w.strip("?.!") in _FOLLOWUP_PRONOUNS for w in words):
        return True
    return False


def last_search_query(history: list[tuple[str, str]], fallback: str) -> str:
    """Return the most recent *substantive* user query (skipping follow-ups).

    ``history`` is a list of (role, content) tuples oldest-first. Used so a
    follow-up ("which is best?") reuses the real search ("career fairs at BCIT")
    for retrieval instead of searching for the follow-up text itself.
    """

    for role, content in reversed(history):
        if role == "user" and content.strip() and not is_followup(content):
            return content
    return fallback


def _day_start(d: datetime) -> datetime:
    return datetime.combine(d.date(), time(0, 0), tzinfo=_PACIFIC)


def _day_end(d: datetime) -> datetime:
    return datetime.combine(d.date(), time(23, 59, 59), tzinfo=_PACIFIC)


def _utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc)


def _word(pattern: str, text: str) -> bool:
    return re.search(rf"\b{pattern}\b", text) is not None


def _detect_time_label(q: str) -> str | None:
    """Detect a relative time phrase in the query (order = most specific first)."""

    if "tomorrow" in q:
        return "tomorrow"
    if "tonight" in q:
        return "tonight"
    if _word("today", q) or "right now" in q:
        return "today"
    if "weekend" in q:
        return "this weekend"
    if "next week" in q:
        return "next week"
    if "this week" in q or _word("week", q):
        return "this week"
    if "next month" in q:
        return "next month"
    if "this month" in q or _word("month", q):
        return "this month"
    return None


def _window_for_label(
    label: str | None, now_utc: datetime
) -> tuple[datetime | None, datetime | None]:
    """Resolve a canonical time label to (after, before) UTC bounds."""

    if label is None:
        return None, None

    local_now = now_utc.astimezone(_PACIFIC)
    today = local_now
    weekday = local_now.weekday()  # Mon=0 .. Sun=6

    if label == "tomorrow":
        d = today + timedelta(days=1)
        return _utc(_day_start(d)), _utc(_day_end(d))
    if label == "tonight":
        start = local_now.replace(hour=17, minute=0, second=0, microsecond=0)
        return _utc(max(local_now, start)), _utc(_day_end(today))
    if label == "today":
        return now_utc, _utc(_day_end(today))
    if label == "this weekend":
        days_to_sat = (5 - weekday) % 7
        sat = today + timedelta(days=days_to_sat)
        if weekday >= 5:  # already Saturday or Sunday
            sat = today - timedelta(days=weekday - 5)
        sun = sat + timedelta(days=1)
        return _utc(_day_start(sat)), _utc(_day_end(sun))
    if label == "next week":
        next_mon = today + timedelta(days=(7 - weekday))
        next_sun = next_mon + timedelta(days=6)
        return _utc(_day_start(next_mon)), _utc(_day_end(next_sun))
    if label == "this week":
        days_to_sun = 6 - weekday
        return now_utc, _utc(_day_end(today + timedelta(days=days_to_sun)))
    if label == "this month":
        first_next = _first_of_next_month(today)
        return now_utc, _utc(first_next - timedelta(seconds=1))
    if label == "next month":
        start = _first_of_next_month(today)
        end = _first_of_next_month(start) - timedelta(seconds=1)
        return _utc(start), _utc(end)
    return None, None


def _first_of_next_month(d: datetime) -> datetime:
    if d.month == 12:
        return datetime(d.year + 1, 1, 1, tzinfo=_PACIFIC)
    return datetime(d.year, d.month + 1, 1, tzinfo=_PACIFIC)


def parse_intent(query: str, now: datetime | None = None) -> QueryIntent:
    """Parse a query into structured retrieval filters.

    Args:
        query: The student's free-text query.
        now: Reference instant (timezone-aware UTC); defaults to current time.

    Returns:
        A :class:`QueryIntent` with any time window, free-food, and campus
        constraints detected in the text. Absent signals stay ``None``/``False``
        so the caller can fall back to UI filters and pure semantic ranking.
    """

    now_utc = now or datetime.now(timezone.utc)
    q = query.lower()

    intent = QueryIntent()

    if any(phrase in q for phrase in _FREE_FOOD_PHRASES):
        intent.require_free_food = True

    for alias, campus in _CAMPUS_ALIASES:
        if _word(re.escape(alias), q):
            intent.campus = campus
            break

    intent.time_label = _detect_time_label(q)
    intent.starts_after, intent.starts_before = _window_for_label(
        intent.time_label, now_utc
    )

    intent.topic = _detect_topic(q)

    logger.debug("parse_intent(%r) -> %s", query, intent.as_dict())
    return intent


_LLM_SYSTEM = (
    "You extract search filters from a student's campus-events query. "
    "Return ONLY a JSON object with keys: "
    'campus (one of "UBC","SFU","BCIT","Douglas" or null), '
    'timeframe (one of "today","tonight","tomorrow","this weekend",'
    '"this week","next week","this month" or null), '
    "free_food (boolean — true only if they want free food/snacks), "
    "topic (a 1-4 word theme like \"career\", \"live music\", \"board games\", "
    "or null). Infer from meaning, not just keywords (e.g. \"grab a bite\" -> "
    "free_food only if they imply free; \"before my night class\" -> today). "
    "Never invent a campus that isn't implied. Output only the JSON."
)


async def refine_intent_llm(
    query: str,
    base: QueryIntent,
    *,
    api_key: str | None,
    model: str,
    now: datetime | None = None,
) -> QueryIntent:
    """Augment rule-based intent with an LLM pass for fuzzier phrasing.

    Additive and safe: the LLM only fills gaps the rules left open (it never
    overrides an explicit rule match), and any failure returns ``base``
    unchanged so the request never fails on the model.
    """

    if not api_key:
        return base
    now_utc = now or datetime.now(timezone.utc)
    payload = {
        "model": model,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _LLM_SYSTEM},
            {"role": "user", "content": query},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            resp.raise_for_status()
        data = json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception:
        logger.debug("refine_intent_llm failed; using rules only", exc_info=True)
        return base

    if not isinstance(data, dict):
        return base

    # Rules win on explicit matches; the LLM only fills what's still open.
    campus = data.get("campus")
    if base.campus is None and isinstance(campus, str):
        for _, canonical in _CAMPUS_ALIASES:
            if campus.strip().lower() == canonical.lower():
                base.campus = canonical
                break

    if not base.require_free_food and data.get("free_food") is True:
        base.require_free_food = True

    if base.time_label is None:
        tf = data.get("timeframe")
        if isinstance(tf, str) and tf.strip().lower() in _TIME_LABELS:
            base.time_label = tf.strip().lower()
            base.starts_after, base.starts_before = _window_for_label(
                base.time_label, now_utc
            )

    if base.topic is None:
        topic = data.get("topic")
        if isinstance(topic, str) and topic.strip():
            base.topic = topic.strip()[:40]

    logger.debug("refine_intent_llm(%r) -> %s", query, base.as_dict())
    return base
