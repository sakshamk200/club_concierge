"""Event search route (Stage 02 hybrid retrieval)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.api.deps import get_retrieval_service
from app.models.chat import SearchRequest, SearchResponse
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])


def _campus_filter(campus: str) -> str | None:
    """Map the 'All' toggle to no campus constraint."""

    return None if campus == "All" else campus


@router.get("/events/upcoming")
async def upcoming_events(
    campus: str | None = None,
    limit: int = 12,
    interests: str | None = None,
    retrieval: RetrievalService = Depends(get_retrieval_service),
) -> dict[str, object]:
    """Soonest upcoming events for the browse grid, optionally personalised."""

    interest_list = [i.strip() for i in (interests or "").split(",") if i.strip()]
    results = await retrieval.upcoming(
        limit=min(max(limit, 1), 24),
        campus=None if campus in (None, "", "All") else campus,
        interests=interest_list,
    )
    return {"results": results}


@router.post("/events/search", response_model=SearchResponse)
async def search_events(
    payload: SearchRequest,
    retrieval: RetrievalService = Depends(get_retrieval_service),
) -> SearchResponse:
    """Run hybrid vector + metadata search and return ranked event cards."""

    logger.debug("search_events query=%r campus=%s", payload.query, payload.campus)
    results = await retrieval.search(
        payload.query,
        limit=payload.limit,
        campus=_campus_filter(payload.campus),
        require_free_food=payload.free_food_only,
    )
    return SearchResponse(
        query=payload.query,
        campus=payload.campus,
        free_food_only=payload.free_food_only,
        results=results,
    )
