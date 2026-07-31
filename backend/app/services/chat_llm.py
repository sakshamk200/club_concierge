"""Conversational answer generation.

Two answerers behind a common :class:`Answerer` protocol:

* :class:`OpenAIAnswerer` — calls an OpenAI chat model to produce a friendly,
  grounded reply. The system prompt strictly constrains the model to the
  retrieved events (the proposal's hallucination-free requirement): it must not
  invent events and must say so when nothing matched. Used when
  ``OPENAI_API_KEY`` is configured.

* :class:`TemplateAnswerer` — the offline, deterministic fallback that wraps
  :func:`app.services.rag.compose_answer`. No key required.

Either way, retrieval happens first and only verified events are passed in, so
the answer is always grounded in real database records.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Protocol

import httpx

from app.config import Settings, get_settings
from app.models.event import EventSearchResult
from app.services.rag import compose_answer

logger = logging.getLogger(__name__)


def _build_user_content(
    query: str,
    results: list[EventSearchResult],
    campus: str | None,
    require_free_food: bool,
) -> str:
    """Compose the grounded user turn with human-readable, dated context."""

    now = datetime.now(timezone.utc)
    context = []
    for r in results:
        when_human = None
        days_out = None
        if r.event_timestamp is not None:
            when_human = r.event_timestamp.strftime("%A %b %d, %I:%M %p")
            days_out = (r.event_timestamp - now).days
        context.append(
            {
                "title": r.title,
                "organizer": r.organizer,
                "location": r.location,
                "campus": r.campus,
                "when": when_human,
                "days_from_now": days_out,
                "free_food": r.has_free_food,
            }
        )
    today = now.strftime("%A %b %d")
    return (
        f"Today is {today}.\n"
        f"Student asked: {query}\n"
        f"Active filters — campus: {campus or 'any'}, "
        f"free food only: {require_free_food}\n"
        f"Verified events you may recommend (JSON):\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )

_SYSTEM_PROMPT = (
    "You are Club Concierge — a sharp, upbeat campus events guide for UBC, SFU, "
    "BCIT and Douglas. You help students decide what to actually go to.\n"
    "\n"
    "Rules:\n"
    "- Use ONLY the events in the latest context JSON. Never invent events, "
    "dates, or locations. If a detail isn't in the data, don't state it.\n"
    "- Lead with a genuine recommendation, not a list. Pick the 1-2 best matches "
    "and say briefly WHY they fit the ask (timing, free food, vibe, it's this "
    "week, etc.). The UI already shows full event cards, so don't repeat every "
    "field.\n"
    "- This is a conversation. If the student follows up ('which is best?', "
    "'choose one', 'the second one', 'tell me more'), commit to ONE specific "
    "event from the context and justify it in a sentence — do NOT re-list "
    "everything or say there's nothing to choose from when events are present.\n"
    "- Be concise and warm: 2-3 sentences, like a friend who knows what's on. A "
    "touch of personality is good; filler and hype are not.\n"
    "- When the ask has a nuance (free food, chill, career, weekend), acknowledge "
    "it so the student feels understood.\n"
    "- If the context is truly empty, say so honestly in one line and suggest a "
    "concrete tweak (different campus, broader terms, or check back after a "
    "refresh). Never pretend there's something when there isn't."
)


class Answerer(Protocol):
    """Common interface for grounded answer generators."""

    async def answer(
        self,
        query: str,
        results: list[EventSearchResult],
        *,
        campus: str | None,
        require_free_food: bool,
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        """Return a grounded natural-language answer."""


class TemplateAnswerer:
    """Offline deterministic answerer (no LLM)."""

    async def answer(
        self,
        query: str,
        results: list[EventSearchResult],
        *,
        campus: str | None,
        require_free_food: bool,
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        return compose_answer(
            query, results, campus=campus, require_free_food=require_free_food
        )


class OpenAIAnswerer:
    """OpenAI-compatible chat-completions answerer (also used for Groq).

    Constrained to the retrieved events. ``base_url`` defaults to OpenAI but can
    point at any OpenAI-compatible endpoint (e.g. Groq).
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1/chat/completions",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._URL = base_url

    async def answer(
        self,
        query: str,
        results: list[EventSearchResult],
        *,
        campus: str | None,
        require_free_food: bool,
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        user_content = _build_user_content(
            query, results, campus, require_free_food
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": _SYSTEM_PROMPT}
        ]
        # Prior turns give the model the thread so follow-ups resolve. Keep the
        # last few (trimmed) and map our "bot" role to the API's "assistant".
        for role, content in (history or [])[-4:]:
            messages.append(
                {
                    "role": "assistant" if role == "bot" else "user",
                    "content": content[:600],
                }
            )
        messages.append({"role": "user", "content": user_content})
        payload = {
            "model": self._model,
            "temperature": 0.55,
            "messages": messages,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        logger.debug(
            "OpenAIAnswerer request (%d events, %d history)",
            len(results),
            len(history or []),
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self._URL, headers=headers, json=payload
                )
                # Free-tier rate limit: brief backoff, single retry.
                if response.status_code == 429:
                    await asyncio.sleep(2.0)
                    response = await client.post(
                        self._URL, headers=headers, json=payload
                    )
                response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            # Signal failure so a fallback provider (or the template) can run.
            logger.warning("OpenAIAnswerer failed", exc_info=True)
            raise


class GeminiAnswerer:
    """Google Gemini answerer (free tier) constrained to retrieved events."""

    _BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def answer(
        self,
        query: str,
        results: list[EventSearchResult],
        *,
        campus: str | None,
        require_free_food: bool,
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        user_content = _build_user_content(
            query, results, campus, require_free_food
        )
        url = f"{self._BASE}/{self._model}:generateContent"
        contents: list[dict[str, object]] = []
        for role, content in (history or [])[-4:]:
            contents.append(
                {
                    "role": "model" if role == "bot" else "user",
                    "parts": [{"text": content[:600]}],
                }
            )
        contents.append({"role": "user", "parts": [{"text": user_content}]})
        payload = {
            "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.55, "maxOutputTokens": 250},
        }
        logger.debug("GeminiAnswerer request (%d events)", len(results))
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url, params={"key": self._api_key}, json=payload
                )
                response.raise_for_status()
            data = response.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
            if not text:
                raise ValueError("empty Gemini answer")
            return text
        except Exception:
            logger.warning("GeminiAnswerer failed", exc_info=True)
            raise


class FallbackAnswerer:
    """Try each provider in order; drop to the offline template if all fail.

    Keeps the chat resilient when a free-tier provider is rate-limited — e.g.
    Groq 429s and Gemini answers instead — so the student still gets a real,
    conversational reply rather than the deterministic template.
    """

    def __init__(self, providers: list[Answerer]) -> None:
        self._providers = providers

    async def answer(
        self,
        query: str,
        results: list[EventSearchResult],
        *,
        campus: str | None,
        require_free_food: bool,
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        for provider in self._providers:
            try:
                return await provider.answer(
                    query,
                    results,
                    campus=campus,
                    require_free_food=require_free_food,
                    history=history,
                )
            except Exception:
                continue
        logger.info("All LLM answerers failed; using offline template")
        return compose_answer(
            query, results, campus=campus, require_free_food=require_free_food
        )


_SMALLTALK_SYSTEM = (
    "You are Club Concierge, a sharp and friendly campus events guide for UBC, "
    "SFU, BCIT and Douglas. The user sent a greeting or casual message. Reply in "
    "one or two natural sentences with a little personality, then nudge them with "
    "a concrete example of what to ask — e.g. 'free food this week', 'career "
    "fairs', or 'something chill this weekend'. Don't list real events, don't use "
    "bullet points, and don't be robotic or over-eager."
)

# Heuristic: short greetings / casual openers that are NOT event queries.
_SMALLTALK_TRIGGERS = (
    "hi", "hii", "hey", "hello", "yo", "sup", "wassup", "what's up", "whats up",
    "how are you", "how's it going", "hows it going", "good morning",
    "good afternoon", "good evening", "thanks", "thank you", "thx", "ok", "okay",
    "cool", "nice", "lol", "who are you", "what can you do", "help",
)

# Words that indicate a real event search even within a short message.
_EVENT_HINTS = (
    "event", "free", "food", "today", "tonight", "week", "weekend", "workshop",
    "club", "career", "fair", "study", "tutor", "lab", "music", "fun", "near",
    "happening", "this", "tomorrow", "campus", "ubc", "douglas",
)


def is_smalltalk(message: str) -> bool:
    """Return True if a message is a greeting / casual opener, not a search."""

    m = message.strip().lower().rstrip("!.?")
    if not m:
        return True
    if any(hint in m for hint in _EVENT_HINTS):
        return False
    if m in _SMALLTALK_TRIGGERS:
        return True
    # Short messages that start with a greeting word.
    if len(m.split()) <= 4 and any(
        m.startswith(t) for t in _SMALLTALK_TRIGGERS
    ):
        return True
    return False


async def smalltalk_reply(message: str, settings: Settings | None = None) -> str:
    """Generate a friendly conversational reply (no events)."""

    settings = settings or get_settings()
    fallback = (
        "Hey! \U0001f44b I'm your campus event concierge for UBC and Douglas. "
        "What are you in the mood for — free food, workshops, clubs, career "
        "events, or something chill this week?"
    )

    key = settings.groq_api_key
    if not key:
        return fallback

    url = "https://api.groq.com/openai/v1/chat/completions"
    model = settings.groq_model

    payload = {
        "model": model,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": _SMALLTALK_SYSTEM},
            {"role": "user", "content": message},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url, headers={"Authorization": f"Bearer {key}"}, json=payload
            )
            response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        logger.error("smalltalk_reply failed; using fallback", exc_info=True)
        return fallback


def get_answerer(settings: Settings | None = None) -> Answerer:
    """Return a resilient answerer chain (Groq → Gemini → offline template)."""

    settings = settings or get_settings()
    providers: list[Answerer] = []
    if settings.groq_api_key:
        providers.append(
            OpenAIAnswerer(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                base_url="https://api.groq.com/openai/v1/chat/completions",
            )
        )
    if settings.gemini_api_key:
        providers.append(
            GeminiAnswerer(
                api_key=settings.gemini_api_key, model=settings.gemini_model
            )
        )
    if not providers:
        logger.debug("No LLM keys; using TemplateAnswerer (offline)")
        return TemplateAnswerer()
    logger.debug("Using FallbackAnswerer with %d provider(s)", len(providers))
    return FallbackAnswerer(providers)
