"""Instagram adapter — Apify scraping + free vision-LLM flyer reading.

The cost-efficient Instagram path:

* **Apify** (`instagram-profile-scraper`) fetches the latest posts from each
  configured campus account — capped at ~10 per handle so a full run costs
  pennies of the free-plan credit.
* **Google Gemini** (a free multimodal model) *looks at the post image*
  together with its caption and extracts structured event fields — the
  proposal's Vision-LLM stage. If the image can't be read (no Gemini key, out
  of quota, or a decommissioned model), it falls back to caption-only
  extraction on the free Groq text model, so ingestion always runs.

  (Groq previously served this vision stage via Llama-4 Scout, but Groq
  removed its vision models in 2026 — hence the Gemini-first design.)

Posts that don't announce a concrete upcoming event are skipped. Activated
automatically when ``APIFY_API_TOKEN`` is configured.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone

import httpx

from app.config import Settings, get_settings
from app.integrations.sources.base import RawEvent
from app.integrations.sources.util import parse_iso_date

logger = logging.getLogger(__name__)

def _extract_prompt() -> str:
    """System prompt anchored to today so undated years resolve forward."""

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return (
        f"Today is {today}. You read a university club's Instagram post (the "
        "flyer image and its caption) and decide whether it announces a "
        "specific upcoming event. Respond with ONLY a JSON object: "
        '{"is_event": bool, "title": string, "start_iso": string|null, '
        '"location": string|null, "campus": "UBC"|"SFU"|"BCIT"|"Douglas"|null, '
        '"free_food": bool}. '
        "is_event is true only for a concrete event with a date or day. When "
        "the post gives a date without a year, resolve it to the NEAREST "
        "FUTURE occurrence relative to today. If the event is clearly in the "
        "past, set is_event to false. Read details from the flyer image when "
        "present. Never invent details."
    )

# Handle -> campus, so a post is tagged even when the flyer text doesn't name
# the school. Must cover every handle in ``club_handles`` (config).
_HANDLE_CAMPUS = {
    # UBC
    "universityofbc": "UBC",
    "amsubc": "UBC",
    "ubcevents": "UBC",
    "ubccsss": "UBC",
    "nwplusubc": "UBC",
    "ubcsus": "UBC",
    "aus_ubc": "UBC",
    "ubcengineers": "UBC",
    "ubcrec": "UBC",
    "ubcbiztech": "UBC",
    "ubcdanceclub": "UBC",
    # SFU
    "simonfraseru": "SFU",
    "sfss": "SFU",
    "sfss_": "SFU",
    "sfusurge": "SFU",
    "sfurecreation": "SFU",
    "sfu_csss": "SFU",
    # BCIT
    "bcit": "BCIT",
    "bcitsa": "BCIT",
    # Douglas
    "douglascollege": "Douglas",
    "thedsu": "Douglas",
    "thedsu6": "Douglas",
}

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class InstagramAdapter:
    """Fetch campus posts via Apify and read flyers with a free vision model."""

    name = "instagram"

    def __init__(
        self,
        *,
        apify_token: str,
        actor_id: str,
        handles: list[str],
        groq_api_key: str | None,
        groq_model: str,
        gemini_api_key: str | None = None,
        gemini_vision_model: str = "gemini-flash-latest",
        posts_per_handle: int = 10,
    ) -> None:
        self._token = apify_token
        self._actor = actor_id.replace("/", "~")
        self._handles = handles
        self._groq_key = groq_api_key
        self._groq_model = groq_model
        self._gemini_key = gemini_api_key
        self._gemini_model = gemini_vision_model
        self._per_handle = posts_per_handle

    async def fetch(self, limit: int) -> list[RawEvent]:
        if not self._groq_key:
            logger.warning("Instagram adapter needs a Groq key for extraction")
            return []

        posts = await self._fetch_posts()
        events: list[RawEvent] = []
        for post in posts:
            if len(events) >= limit:
                break
            extracted = await self._extract(post)
            if extracted is not None:
                events.append(extracted)
        logger.info("Instagram: %d posts -> %d events", len(posts), len(events))
        return events

    async def _fetch_posts(self) -> list[dict[str, object]]:
        """Run the Apify actor and return flattened, capped post items.

        The profile-scraper actor returns one item per profile with a
        ``latestPosts`` array; other actors return flat post items. Both
        shapes are handled, capped to ``posts_per_handle`` per account.
        """

        url = (
            "https://api.apify.com/v2/acts/"
            f"{self._actor}/run-sync-get-dataset-items"
        )
        payload = {
            "usernames": self._handles,
            "resultsLimit": self._per_handle,
        }
        logger.info("Apify Instagram run for %s", self._handles)
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    url, params={"token": self._token}, json=payload
                )
                response.raise_for_status()
                items = response.json()
        except Exception:
            logger.error("Apify Instagram scrape failed", exc_info=True)
            return []

        posts: list[dict[str, object]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("latestPosts"), list):
                owner = item.get("username") or item.get("ownerUsername")
                for post in item["latestPosts"][: self._per_handle]:
                    if isinstance(post, dict):
                        post.setdefault("ownerUsername", owner)
                        posts.append(post)
            elif item.get("caption") or item.get("displayUrl"):
                posts.append(item)
        logger.debug("Apify returned %d posts after flattening", len(posts))
        return posts

    async def _extract(self, post: dict[str, object]) -> RawEvent | None:
        """Read the flyer image (+ caption) and map the event if there is one."""

        caption = str(post.get("caption") or "")[:1500]
        image_url = _as_str(post.get("displayUrl"))
        if not caption and not image_url:
            return None
        handle = str(post.get("ownerUsername") or "club").lower()
        posted_at = _as_str(post.get("timestamp"))
        if posted_at:
            caption = f"(posted on {posted_at[:10]}) {caption}"

        # Flyer-image reading via Gemini when configured; otherwise (or on any
        # failure / quota exhaustion) fall back to caption-only extraction on
        # the free Groq text model, so ingestion always produces events.
        data = None
        if image_url and self._gemini_key:
            data = await self._call_gemini(caption, handle, image_url)
        if data is None and caption:
            data = await self._call_groq(self._groq_model, caption, handle, None)
        if data is None or not data.get("is_event") or not data.get("title"):
            return None

        campus = _as_str(data.get("campus")) or _HANDLE_CAMPUS.get(handle)
        post_url = _as_str(post.get("url")) or image_url
        return RawEvent(
            source=self.name,
            external_id=str(post.get("id") or post.get("shortCode") or post_url),
            title=str(data["title"])[:200],
            url=post_url,
            organizer=f"@{handle}",
            location=_as_str(data.get("location")),
            campus=campus,
            start=parse_iso_date(_as_str(data.get("start_iso"))),
            cost_text="free" if data.get("free_food") else None,
            description=caption[:400],
            image_url=image_url,
        )

    async def _call_groq(
        self,
        model: str,
        caption: str,
        handle: str,
        image_url: str | None,
    ) -> dict[str, object] | None:
        """One extraction attempt against Groq; None on any failure."""

        text = f"Post by @{handle}. Caption:\n{caption or '(no caption)'}"
        content: object
        if image_url:
            content = [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
        else:
            content = text
        payload = {
            "model": model,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _extract_prompt()},
                {"role": "user", "content": content},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    _GROQ_URL,
                    headers={"Authorization": f"Bearer {self._groq_key}"},
                    json=payload,
                )
                if response.status_code == 429:
                    # Free-tier rate limit: brief backoff, single retry.
                    await asyncio.sleep(3.0)
                    response = await client.post(
                        _GROQ_URL,
                        headers={"Authorization": f"Bearer {self._groq_key}"},
                        json=payload,
                    )
                response.raise_for_status()
            parsed = json.loads(
                response.json()["choices"][0]["message"]["content"]
            )
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            logger.debug("Groq extraction attempt failed (%s)", model, exc_info=True)
            return None

    async def _call_gemini(
        self, caption: str, handle: str, image_url: str
    ) -> dict[str, object] | None:
        """Read the flyer image with Gemini; None on any failure.

        Downloads the image, sends it inline (base64) with the caption and the
        JSON-extraction prompt, and forces a JSON response. Any error (missing
        quota, decommissioned model, network) returns None so the caller falls
        back to caption-only extraction.
        """

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._gemini_model}:generateContent"
        )
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                img = await client.get(
                    image_url, headers={"User-Agent": "Mozilla/5.0 (ClubConcierge)"}
                )
                img.raise_for_status()
                mime = img.headers.get("content-type", "image/jpeg").split(";")[0]
                b64 = base64.b64encode(img.content).decode("ascii")
                payload = {
                    "system_instruction": {"parts": [{"text": _extract_prompt()}]},
                    "contents": [
                        {
                            "parts": [
                                {
                                    "text": f"Post by @{handle}. "
                                    f"Caption:\n{caption or '(no caption)'}"
                                },
                                {"inline_data": {"mime_type": mime, "data": b64}},
                            ]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.0,
                        "response_mime_type": "application/json",
                    },
                }
                response = await client.post(
                    url, params={"key": self._gemini_key}, json=payload
                )
                response.raise_for_status()
            body = response.json()
            text = body["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            logger.debug("Gemini extraction attempt failed", exc_info=True)
            return None


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def maybe_instagram_adapter(
    settings: Settings | None = None,
) -> InstagramAdapter | None:
    """Return a configured adapter, or None when no Apify token is set."""

    settings = settings or get_settings()
    if not settings.apify_api_token:
        return None
    return InstagramAdapter(
        apify_token=settings.apify_api_token,
        actor_id=settings.apify_actor_id,
        handles=settings.club_handle_list,
        groq_api_key=settings.groq_api_key,
        groq_model=settings.groq_model,
        gemini_api_key=settings.gemini_api_key,
        gemini_vision_model=settings.gemini_vision_model,
        posts_per_handle=settings.instagram_posts_per_handle,
    )
