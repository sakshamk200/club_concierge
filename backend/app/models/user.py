"""Application user data contracts.

``AppUser`` mirrors ``public.app_users`` (internal — includes the password
hash). ``UserPublic`` is the shape returned to the frontend: never the hash.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AppUser(BaseModel):
    """Internal account row, including the stored password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str
    password_hash: str = Field(repr=False)
    campus: str | None = None
    program: str | None = None
    interests: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def public(self) -> "UserPublic":
        """Strip private fields for API responses."""

        return UserPublic(
            id=self.id,
            email=self.email,
            name=self.name,
            campus=self.campus,
            program=self.program,
            interests=self.interests,
        )


class UserPublic(BaseModel):
    """Account shape safe to send to the client."""

    id: UUID
    email: str
    name: str
    campus: str | None = None
    program: str | None = None
    interests: list[str] = Field(default_factory=list)
