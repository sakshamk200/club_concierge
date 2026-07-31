"""Request/response contracts for the chat and search endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.event import EventSearchResult

CampusFilter = Literal["UBC", "SFU", "BCIT", "Douglas", "All"]


class ChatMessage(BaseModel):
    """One prior turn of the conversation, for follow-up context."""

    role: Literal["user", "bot"]
    content: str = Field(max_length=4000)


class SearchRequest(BaseModel):
    """A natural-language search/chat request from the frontend."""

    query: str = Field(min_length=1, description="Student's free-text query.")
    campus: CampusFilter = Field(
        default="All", description="Campus scope toggle."
    )
    free_food_only: bool = Field(
        default=False, description="Restrict to free-food events."
    )
    interests: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Student's profile interests, for preference-aware ranking.",
    )
    history: list[ChatMessage] = Field(
        default_factory=list,
        max_length=20,
        description="Recent conversation turns, oldest first, for follow-ups.",
    )
    limit: int = Field(default=6, ge=1, le=25)


class SearchResponse(BaseModel):
    """Search results plus the active filter echo."""

    query: str
    campus: CampusFilter
    free_food_only: bool
    results: list[EventSearchResult]


class UnderstoodIntent(BaseModel):
    """The filters the concierge parsed from the query, for UI display."""

    campus: str | None = None
    time_label: str | None = None
    free_food: bool = False
    topic: str | None = None


class ChatResponse(SearchResponse):
    """Search results plus a grounded natural-language answer."""

    answer: str
    understood: UnderstoodIntent = Field(default_factory=UnderstoodIntent)
