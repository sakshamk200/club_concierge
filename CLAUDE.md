# Club & Event Concierge — Project Source of Truth

Conversational, hallucination-free campus event discovery for **UBC · SFU · BCIT ·
Douglas College**. Students ask in natural language; the concierge answers grounded
**only** in real, verified events scraped from campus calendars and club Instagram
flyers — with time / campus / free-food / theme understanding, conversation memory,
and preference-aware ranking.

## Team Matrix

| Name | Course |
|---|---|
| Mohammadullah Akbari | CSIS 4495 – 071 |
| Saksham Kakkar | CSIS 4495 – 071 |

---

## Stack Primitives

- **Runtime:** Python 3.11+ (3.13 verified) · Node.js 18+
- **Web Framework:** FastAPI with lifespan-managed async context (`@asynccontextmanager`
  lifespan, not deprecated `on_event` hooks)
- **HTTP Client:** HTTPX (async) for all outbound HTTP calls
- **Database:** Supabase Postgres + **pgvector** via a raw **asyncpg** wrapper — no ORM,
  raw async queries only. HNSW index (m=16, ef_construction=64), hybrid cosine + metadata SQL.
- **Frontend:** Next.js (App Router, TypeScript)
- **AI providers (direct calls, no orchestration framework):**
  - *Embeddings* — deterministic local hashing vectorizer (1536-dim, offline, no key)
  - *Chat + query understanding* — **Groq** (`llama-3.3-70b-versatile`)
  - *Flyer-image vision* — **Google Gemini** (`gemini-flash-latest`)
  - *Instagram scraping* — **Apify**
  - Resilient fallback chain everywhere: Groq → Gemini → deterministic template

---

## Architecture at a Glance

- **Ingestion (source-agnostic):** each adapter yields normalised `RawEvent`s through one
  pipeline — `dedup (MD5) → content hash (SHA-256) → free-event filter → validate → embed →
  store`. Adapters: `TheEventsCalendarAdapter` (UBC AMS, BCIT SA), `LiveWhaleAdapter` (SFU),
  `SquarespaceEventsAdapter` (Douglas DSU), `InstagramAdapter` (Apify + Gemini vision).
- **Query understanding:** rule-based parser (time windows, campus, free-food, theme) plus a
  gated Groq LLM pass for fuzzy phrasing; surfaced to the user as *"Understood"* chips.
- **Conversation memory:** recent turns travel with each request so follow-ups
  ("which is best?", "choose one") resolve against the events already shown.
- **Retrieval:** hybrid pgvector cosine + metadata filters, interest-boosted re-ranking.
- **Auth:** PBKDF2-SHA256 hashing, HMAC-signed stateless sessions, Google Identity Services.

---

## System Conventions

### Async I/O
Every async I/O wrapper (database calls, HTTP calls, external service clients) must implement
structured logging via the Python `logging` module. Use `logging.getLogger(__name__)` per
module. Log at DEBUG for entry/exit of I/O boundaries and ERROR with exc_info for exceptions.

### Type Hinting
Explicit type hints are required across **all** function boundaries — parameters and return
types. No `Any` unless genuinely unavoidable and documented with a comment explaining why.
Use `from __future__ import annotations` at the top of every module.

### Resilience
External providers can rate-limit or change. Every LLM / vision / scrape path must degrade
gracefully (fallback provider, then a deterministic path) so a single failure never breaks a
request or the ingestion run.

---

## Campus Context & Domain Insight

Four schools are supported. Campus is trusted for official on-campus feeds and inferred from
event text for third-party sources. Temporal relevance is enforced via natural-language time
windows (today / tonight / this weekend / next week / next month, resolved in Pacific time).

- **UBC** — high-volume residential discovery; evening- and weekend-heavy; events near the AMS
  Student Nest (6133 University Blvd).
- **SFU** — mountain/commuter mix; society + big-club activity.
- **BCIT** — career- and trades-focused; strong career-services event volume.
- **Douglas College** — transit-bound commuter students; daytime clusters, hard time cutoffs
  around transit windows — surfaced through the time-window filtering above.

---

## Non-Negotiable Code Rules

1. **Write every line of code completely.** No truncation of any kind.
2. **No placeholder blocks.** Do not emit `pass`, `...`, or `# TODO` as a substitute for real
   implementation.
3. **No stub comments.** Never append `# Write implementation here`, `# implement this`, or
   equivalent.
4. **Every file must be complete, compilable, and production-ready** before it is written to disk.
5. Partial implementations that cannot be imported and executed are not acceptable deliverables.
