<div align="center">

# 🎓 Club & Event Concierge

**Ask in plain English. Get real campus events — never a made-up one.**

A conversational, hallucination-free event concierge for **UBC · SFU · BCIT · Douglas College**.
Students ask things like *"free pizza this weekend at SFU"* or *"I want a job next month, which events help?"*
and get grounded answers pulled from live campus calendars and club Instagram flyers.

CSIS 4495 · **Mohammadullah Akbari** & **Saksham Kakkar**

</div>

---

## 🔑 Demo account

Skip sign-up — log in with the ready-made account (home campus + interests already set,
so preference-aware ranking is visible immediately):

| Email | Password |
|---|---|
| `demo@clubconcierge.app` | `ClubDemo2026` |

> Or click **Continue with Google**, or register a fresh account in ~20 seconds.

---

## ✨ What it does

- 🧠 **Understands the question.** A rule + LLM intent layer parses **time** ("tonight",
  "this weekend", "next month"), **campus**, **free-food**, and **theme** ("get a job" → career)
  out of natural language, then applies them as real filters — shown back as *"Understood"* chips.
- 💬 **Real conversation.** Remembers the thread, so follow-ups work: *"which is best?"*,
  *"choose one"*, *"tell me more"* commit to a specific event instead of restarting.
- 🛡️ **Never hallucinates.** Every answer is grounded strictly in retrieved, verified events —
  if there's nothing, it says so.
- 🖼️ **Reads the flyers.** Club Instagram posters become searchable events via vision AI.
- ⭐ **Personalized.** Profile interests re-rank results and light up *"✨ For you"* badges.
- 📅 **Actionable.** One-tap **Add to calendar** and a link back to the official source on every card.

---

## 🏗️ How it works

**Ingestion (source-agnostic).** Each adapter yields normalised `RawEvent`s through one pipeline:
`dedup (MD5) → content hash (SHA-256) → free-event filter → validate → embed → store`.

| Campus | Source | Adapter |
|---|---|---|
| UBC (AMS) · BCIT (SA) | The Events Calendar REST API | `TheEventsCalendarAdapter` |
| SFU | LiveWhale events JSON feed | `LiveWhaleAdapter` |
| Douglas (DSU) | Squarespace events (`?format=json`) | `SquarespaceEventsAdapter` |
| Clubs | Instagram flyers via Apify + **Gemini vision** | `InstagramAdapter` |

**Retrieval & AI.**
- *Embeddings* — deterministic local hashing vectorizer (1536-dim, offline, no key).
- *Query understanding* — fast regex rules + a gated Groq LLM pass for fuzzy phrasing.
- *Answering* — grounded RAG with a resilient **Groq → Gemini → template** fallback chain.
- *Ranking* — hybrid cosine + metadata SQL over pgvector (HNSW, m=16), interest-boosted.

**Stack:** FastAPI (async) · asyncpg · Supabase Postgres + pgvector · Next.js (App Router, TS) ·
Groq · Google Gemini · Apify · PBKDF2 auth + Google Identity Services.

---

## 🚀 Run it

**Prerequisites:** Python 3.11+ · Node.js 18+ · internet (DB + AI are cloud-hosted; no local Postgres).

### Backend — port 8000
```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[ai]"
.venv/Scripts/python scripts/apply_migrations.py   # idempotent schema
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```
Load real events (scrape → dedup → embed → store), then browse the docs:
```bash
curl -X POST http://127.0.0.1:8000/admin/ingest
```
API docs → <http://127.0.0.1:8000/docs>

### Frontend — port 3000
```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```
Open <http://localhost:3000> and log in with the demo account above.

---

## ⚙️ Configuration

Secrets live in git-ignored env files. The app degrades gracefully when a key is absent
(no Gemini → caption-only flyers; no Groq → template answers; no Google ID → email login only).

**`backend/.env`**
```
DATABASE_URL=postgresql://…                       # Supabase Postgres (pgvector)
GROQ_API_KEY=…                                     # chat + fuzzy intent (free tier)
GEMINI_API_KEY=…                                   # flyer-image reading (free tier)
APIFY_API_TOKEN=…                                  # Instagram scraping
GOOGLE_CLIENT_ID=…apps.googleusercontent.com       # optional: Google sign-in
```
**`frontend/.env.local`**
```
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_GOOGLE_CLIENT_ID=…apps.googleusercontent.com   # optional
```

---

## 🎬 Demo script

1. Log in as the demo account → the grid is already ranked for **career / free food / workshops**
   with **✨ For you** badges.
2. Tap **"free pizza this weekend at SFU"** → note the *Understood* chips (SFU · this weekend · 🍕).
3. Type a fuzzy one live: **"I want a job next month, which events will help me?"** → it infers
   **next month** + **career** and recommends the resume workshops & career fairs.
4. Follow up with **"which one is best for a first-year?"** → it commits to a single event.
5. Filter to one campus → results stay strictly campus-bounded (a truthfulness guarantee).

---

## ✅ Endpoints & tests

| Method | Path | Purpose |
|---|---|---|
| POST | `/chat` | Query understanding + grounded answer + cards |
| POST | `/events/search` · GET `/events/upcoming` | Search / browse |
| POST | `/admin/ingest` · `/admin/reset-ingested` | Run / reset a live scrape |
| POST | `/auth/register` · `/auth/login` · `/auth/google` | Auth |
| GET | `/health` | Liveness + DB connectivity |

```bash
cd backend && .venv/Scripts/python -m pytest -q      # 24 passing
```

---

## What's real vs. stand-in

- **Real:** live web + Instagram scraping across four schools, Gemini flyer vision, Groq grounded
  answers, natural-language query understanding + conversation memory, Supabase Postgres + pgvector,
  HNSW index, hybrid cosine + metadata SQL, two-stage MD5/SHA-256 dedup, PBKDF2 auth + Google sign-in.
- **Stand-in:** embeddings use a deterministic local hashing vectorizer (drop-in for a hosted
  embedding model) so retrieval needs no paid key.
