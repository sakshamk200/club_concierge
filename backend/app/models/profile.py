"""Student profile data contract.

Mirrors ``public.user_profiles``. Drives preference-aware filtering: Profile A
(UBC) versus Profile B (Douglas College, where ``transit_cutoff_minutes``
encodes the hard West Coast Express temporal boundary).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StudentProfile(BaseModel):
    """A student's stored preferences."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Primary key referencing auth.users.id.")
    campus: str | None = Field(default=None, description="'UBC' | 'Douglas'.")
    program: str | None = Field(default=None, description="Academic program.")
    interest_tags: list[str] = Field(
        default_factory=list,
        description="Preferred event categories / interest tags.",
    )
    transit_cutoff_minutes: int | None = Field(
        default=None,
        description=(
            "Profile B hard temporal cutoff: minutes-since-midnight of the last "
            "viable West Coast Express departure for the student's corridor."
        ),
    )
    created_at: datetime | None = Field(default=None)
