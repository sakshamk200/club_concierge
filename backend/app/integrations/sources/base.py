"""Source adapter base types and the free-event classifier."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

# Keywords that signal food at an event. Since these are drawn from the "free"
# listings, food-at-a-free-event is treated as free food.
_FREE_FOOD_KEYWORDS = (
    "free food",
    "free pizza",
    "pizza",
    "snack",
    "nibble",
    "refreshment",
    "catered",
    "bbq",
    "barbecue",
    "tasting",
    "brunch",
    "potluck",
    "food truck",
    "coffee",
    "lunch",
    "breakfast",
    "dinner",
    "dessert",
    "complimentary",
)

# Cost strings that unambiguously mean "no charge".
_FREE_COST_LITERALS = {"", "0", "0.0", "0.00", "$0", "$0.00", "free", "no charge", "none"}

_PRICE_RE = re.compile(r"\$\s*([0-9]+(?:\.[0-9]{1,2})?)")

# Keywords marking an event as campus/academic-relevant. Used to filter noisy
# third-party sources down to genuine university/college events.
_CAMPUS_KEYWORDS = (
    "student", "college", "university", "campus", "study", "tutor",
    "lab", "workshop", "career", "academic", "research", "seminar",
    "lecture", "orientation", "scholarship", "faculty", "alumni",
    "undergrad", "graduate", " grad", "education", "course", "class",
    "exam", "hackathon", "club", "fair", "networking", "stem", "science",
    "math", "coding", "volunteer", "internship", "co-op", "resume",
)

# Source names that are inherently campus-official and bypass the filter.
CAMPUS_SOURCES = {
    "ubc_ams", "douglas_dsu", "bcit_sa", "sfu_livewhale", "instagram", "mock",
}


# Other post-secondary institutions — events naming these are not UBC/Douglas.
_OTHER_SCHOOLS = (
    "sfu", "simon fraser", "bcit", "kwantlen", "kpu", "capilano", "capu",
    "corpus christi", "langara", "vcc", "emily carr", "ubc okanagan",
)


def infer_campus(
    title: str, description: str | None, location: str | None
) -> str | None:
    """Infer 'UBC' or 'Douglas' from an event's own text, or None to drop it.

    Used for third-party sources where the search region is not a reliable
    campus signal. Events naming a different school, or not mappable to UBC /
    Douglas by name or city, return None and are discarded.
    """

    blob = f"{title} {description or ''} {location or ''}".lower()

    if "douglas" in blob:
        return "Douglas"
    if "ubc" in blob or "university of british columbia" in blob:
        return "UBC"
    # Explicit other-school events are out of scope.
    if any(school in blob for school in _OTHER_SCHOOLS):
        return None
    # Fall back to city: Douglas campuses vs UBC's city.
    if "new westminster" in blob or "coquitlam" in blob:
        return "Douglas"
    if "vancouver" in blob or "point grey" in blob:
        return "UBC"
    return None


def is_campus_relevant(source: str, title: str, description: str | None) -> bool:
    """Whether an event is a genuine campus/college event.

    On-campus official sources always pass; third-party sources must match an
    academic/campus keyword.
    """

    if source in CAMPUS_SOURCES:
        return True
    blob = f"{title} {description or ''}".lower()
    return any(keyword in blob for keyword in _CAMPUS_KEYWORDS)


# --- Student-relevance scoring ----------------------------------------------
# Campus feeds mix student-facing events with administrative/academic notices
# (thesis defences, senate meetings, closures). We exclude the noise outright
# and rank what remains so the most student-relevant events fill the catalogue.

_EXCLUDE_KEYWORDS = (
    # Cancelled / postponed
    "canceled", "cancelled", "postponed",
    # Academic administration / governance / research seminars
    "thesis defence", "thesis defense", "phd defence", "phd defense",
    "capstone", "project defence", "project defense", "defence:", "defense:",
    "colloquium", "frontiers in", "seminar series", "guest lecture",
    "public lecture", "alumni perspectives", "exhibit",
    "dissertation", "msc defence", "msc defense", "murb", "senate",
    "board of governors", "board meeting", "annual general meeting",
    "exam period", "grades due", "add/drop", "waitlist", "fee deadline",
    "tuition deadline", "statutory holiday", "college closed", "campus closed",
    "office closed", "closure", "faculty meeting", "department meeting",
    "committee meeting", "deadline to withdraw",
    # Faculty / instructor professional development (not student-facing)
    "sotl", "teaching + learning inquiry", "for instructors", "for faculty",
    "curriculum development", "pedagogy workshop", "teaching assistant training",
    # Program marketing aimed at applicants, not current students
    "info-session for master", "info session for master",
    "info-session for graduate", "info session for graduate",
    "program info session", "admissions info", "campus tour",
    "virtual tour", "open house for applicants", "applicant",
)

# Weighted signals of student-life relevance. Higher total = shown first.
_RELEVANCE_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("free food", 5), ("free pizza", 5), ("pizza", 3), ("free", 3),
    ("career fair", 5), ("job fair", 5), ("career", 3), ("hiring", 3),
    ("networking", 4), ("mixer", 4), ("social", 4), ("club", 4),
    ("workshop", 4), ("hackathon", 5), ("game", 3), ("games night", 5),
    ("trivia", 4), ("karaoke", 4), ("movie", 3), ("music", 3),
    ("party", 4), ("fest", 3), ("festival", 3), ("bbq", 4),
    ("volunteer", 3), ("wellness", 3), ("fitness", 2), ("sports", 2),
    ("orientation", 3), ("student", 2), ("resume", 3), ("interview", 3),
    ("co-op", 3), ("internship", 3), ("scholarship", 2), ("study", 2),
    ("tutoring", 3), ("market", 2), ("art", 2), ("paint", 2), ("craft", 3),
    ("night", 2), ("drop-in", 2), ("giveaway", 4), ("prizes", 3),
    ("lunch", 2), ("dinner", 2), ("screening", 3), ("book club", 4),
    ("open mic", 4), ("comedy", 3), ("dance", 3), ("meetup", 3),
)

# Events must clear this score to enter the catalogue — anything weaker is a
# low-signal listing (lectures, notices) students are unlikely to search for.
MIN_RELEVANCE = 1


def is_student_noise(title: str, description: str | None) -> bool:
    """True for administrative/academic-notice items students don't attend."""

    blob = f"{title} {description or ''}".lower()
    return any(keyword in blob for keyword in _EXCLUDE_KEYWORDS)


def relevance_score(title: str, description: str | None) -> int:
    """Score how student-life relevant an event is (higher = more relevant)."""

    blob = f"{title} {description or ''}".lower()
    return sum(weight for keyword, weight in _RELEVANCE_WEIGHTS if keyword in blob)


@dataclass
class RawEvent:
    """A normalised event from any source, prior to validation/embedding."""

    source: str
    external_id: str
    title: str
    url: str | None = None
    organizer: str | None = None
    location: str | None = None
    campus: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    cost_text: str | None = None
    description: str | None = None
    # Image-flyer sources (e.g. Instagram) set these; website sources leave them.
    image_url: str | None = None
    image_bytes: bytes | None = field(default=None, repr=False)
    needs_vision: bool = False


class SourceAdapter(Protocol):
    """Common interface for all event sources."""

    name: str

    async def fetch(self, limit: int) -> list[RawEvent]:
        """Return up to ``limit`` normalised events from this source."""


def classify_free(
    cost_text: str | None, title: str, description: str | None
) -> tuple[bool, bool]:
    """Classify an event as free, and whether it offers free food.

    Returns:
        (is_free, has_free_food)
    """

    cost = (cost_text or "").strip().lower()
    blob = f"{title} {description or ''}".lower()

    is_free = False
    if cost in _FREE_COST_LITERALS:
        is_free = True
    if "free" in cost:
        is_free = True
    if "free" in blob:
        is_free = True

    # An explicit positive price overrides any "free" hint in the cost field.
    match = _PRICE_RE.search(cost)
    if match and float(match.group(1)) > 0:
        is_free = False

    has_free_food = any(keyword in blob for keyword in _FREE_FOOD_KEYWORDS)
    return is_free, has_free_food
