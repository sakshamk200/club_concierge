"""OAuth token data contract.

Mirrors ``public.user_tokens``. Persists the per-provider OAuth 2.0 credentials
(obtained via Authorization Code Flow with PKCE) that the Stage 03 calendar tool
node uses to write events to a student's Google or Microsoft calendar.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CalendarProvider = Literal["google", "microsoft"]


class UserToken(BaseModel):
    """A stored OAuth credential row for one (user, provider) pair."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = Field(default=None)
    user_id: UUID = Field(description="Owning user (auth.users.id).")
    provider: CalendarProvider = Field(description="'google' | 'microsoft'.")
    access_token: str = Field(min_length=1)
    refresh_token: str | None = Field(default=None)
    scope: str | None = Field(default=None)
    token_type: str | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)
