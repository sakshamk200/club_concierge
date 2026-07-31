"""Conversational chat route (retrieval + grounded answer composition)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.api.deps import get_retrieval_service
from app.config import get_settings
from app.models.chat import ChatResponse, SearchRequest, UnderstoodIntent
from app.services.chat_llm import get_answerer, is_smalltalk, smalltalk_reply
from app.services.query_understanding import (
    is_followup,
    last_search_query,
    parse_intent,
    refine_intent_llm,
)
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def _campus_filter(campus: str) -> str | None:
    return None if campus == "All" else campus


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: SearchRequest,
    retrieval: RetrievalService = Depends(get_retrieval_service),
) -> ChatResponse:
    """Answer a student query, grounded strictly in retrieved verified events."""

    logger.debug("chat query=%r campus=%s", payload.query, payload.campus)

    history = [(m.role, m.content) for m in payload.history]

    # Conversational turn (greeting / casual) — reply, don't dump events. A
    # follow-up like "which is best?" is NOT smalltalk even if it's short.
    if is_smalltalk(payload.query) and not is_followup(payload.query):
        answer = await smalltalk_reply(payload.query)
        return ChatResponse(
            query=payload.query,
            campus=payload.campus,
            free_food_only=payload.free_food_only,
            answer=answer,
            results=[],
        )

    # For a follow-up ("which is best?", "choose one"), retrieve using the last
    # real search from the conversation instead of the follow-up text — so we
    # reason over the events already on screen rather than filtering to none.
    search_query = payload.query
    if is_followup(payload.query) and history:
        search_query = last_search_query(history, payload.query)

    # Understand the (effective) query: fast rule-based parse, then an LLM pass
    # for fuzzier phrasing. Merge with the UI filters (an explicit UI campus or
    # free-food toggle wins; otherwise use what the text implies).
    settings = get_settings()
    intent = parse_intent(search_query)
    # Only spend an LLM call on intent when the fast rules found no structured
    # signal (a genuinely fuzzy query) — this keeps most turns to a single Groq
    # call (the answer) and well under the free-tier rate limit.
    if not (intent.campus or intent.time_label or intent.require_free_food):
        intent = await refine_intent_llm(
            search_query,
            intent,
            api_key=settings.groq_api_key,
            model=settings.groq_model,
        )
    ui_campus = _campus_filter(payload.campus)
    campus = ui_campus or intent.campus
    require_free_food = payload.free_food_only or intent.require_free_food

    # Fold the detected theme (e.g. "career") into the ranking signal so the
    # right kind of event floats up even when the wording never says it.
    search_interests = list(payload.interests)
    if intent.topic and intent.topic not in search_interests:
        search_interests.append(intent.topic)

    results = await retrieval.search(
        search_query,
        limit=payload.limit,
        campus=campus,
        require_free_food=require_free_food,
        starts_after=intent.starts_after,
        starts_before=intent.starts_before,
        interests=search_interests,
    )
    answerer = get_answerer()
    answer = await answerer.answer(
        payload.query,
        results,
        campus=campus,
        require_free_food=require_free_food,
        history=history,
    )
    return ChatResponse(
        query=payload.query,
        campus=payload.campus,
        free_food_only=payload.free_food_only,
        answer=answer,
        results=results,
        understood=UnderstoodIntent(
            campus=campus,
            time_label=intent.time_label,
            free_food=require_free_food,
            topic=intent.topic,
        ),
    )
