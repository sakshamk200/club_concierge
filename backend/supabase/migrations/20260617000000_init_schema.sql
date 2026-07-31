-- =============================================================================
-- Club & Event Concierge — Initial Schema
-- Migration: 20260617000000_init_schema.sql
-- Team: Almost Artificial (Mohammadullah Akbari, Saksham Kakkar) — CSIS 4495-071
--
-- Establishes the core persistence layer for the three-stage pipeline:
--   Stage 01 (Ingestion)  -> events.image_hash dedup, raw flyer provenance
--   Stage 02 (Brain/RAG)  -> events.embedding + HNSW index for semantic search
--   Stage 03 (Action)     -> user_profiles for preference-aware filtering
--
-- Target: Supabase managed PostgreSQL with the pgvector extension.
-- Embedding dimensionality: 1536 (OpenAI text-embedding-3-small).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Extensions
-- -----------------------------------------------------------------------------
-- pgvector provides the `vector` type and ANN index access methods (hnsw/ivfflat).
create extension if not exists vector;

-- pgcrypto provides gen_random_uuid() for server-side UUID primary key defaults.
create extension if not exists pgcrypto;

-- -----------------------------------------------------------------------------
-- 2. events — structured, semantically indexed event records
-- -----------------------------------------------------------------------------
create table if not exists public.events (
    id                      uuid primary key default gen_random_uuid(),
    title                   text not null,
    organizer               text,
    location                text,
    campus                  text,                       -- 'UBC' | 'Douglas' (Profile A/B scoping)
    event_timestamp         timestamptz,
    registration_deadline   timestamptz,
    original_image_url      text,
    image_hash              text unique,                -- SHA-256 of flyer binary; dedup key (Stage 01)
    has_free_food           boolean not null default false,
    perks                   text[] not null default '{}',
    embedding               vector(1536),               -- text-embedding-3-small (Stage 02)
    created_at              timestamptz not null default now()
);

-- HNSW index for sub-millisecond approximate nearest-neighbor semantic retrieval.
-- Cosine distance operator class matches normalized OpenAI embeddings.
-- Proposal-mandated build parameters: m = 16, ef_construction = 64.
create index if not exists events_embedding_hnsw_idx
    on public.events
    using hnsw (embedding vector_cosine_ops)
    with (m = 16, ef_construction = 64);

-- Supporting indexes for the hybrid query path (metadata filters combined with
-- vector ranking): campus boundary, temporal range, and perk tag membership.
create index if not exists events_campus_idx
    on public.events (campus);

create index if not exists events_event_timestamp_idx
    on public.events (event_timestamp);

create index if not exists events_perks_gin_idx
    on public.events using gin (perks);

-- -----------------------------------------------------------------------------
-- 3. user_profiles — student preference structures
-- -----------------------------------------------------------------------------
create table if not exists public.user_profiles (
    id                      uuid primary key references auth.users (id) on delete cascade,
    campus                  text,
    program                 text,
    interest_tags           text[] not null default '{}',
    transit_cutoff_minutes  integer,                    -- Profile B: WCE hard temporal cutoff
    created_at              timestamptz not null default now()
);

-- Row-level security: a profile row is readable/writable only by its owner.
alter table public.user_profiles enable row level security;

drop policy if exists user_profiles_select_own on public.user_profiles;
create policy user_profiles_select_own
    on public.user_profiles
    for select
    using (auth.uid() = id);

drop policy if exists user_profiles_modify_own on public.user_profiles;
create policy user_profiles_modify_own
    on public.user_profiles
    for all
    using (auth.uid() = id)
    with check (auth.uid() = id);
