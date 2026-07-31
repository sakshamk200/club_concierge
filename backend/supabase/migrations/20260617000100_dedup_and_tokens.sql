-- =============================================================================
-- Club & Event Concierge — Deduplication & OAuth Token Persistence
-- Migration: 20260617000100_dedup_and_tokens.sql
-- Team: Almost Artificial (Mohammadullah Akbari, Saksham Kakkar) — CSIS 4495-071
--
-- Adds the two supporting tables described in proposal §4.2:
--   processed_hashes -> cost-control deduplication for the Stage 01 Vision-LLM
--                       pipeline (MD5-of-URL + SHA-256-of-binary two-stage check)
--   user_tokens      -> OAuth 2.0 credential persistence for Stage 03 agentic
--                       calendar writes (Google + Microsoft Graph), RLS-scoped
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. processed_hashes — cryptographic deduplication ledger
-- -----------------------------------------------------------------------------
-- The ingestion worker computes an MD5 digest of the image CDN URL for a fast
-- first-stage check, then (on miss) downloads the binary and computes a SHA-256
-- digest for a second-stage check before any Vision-LLM call. Both digests are
-- recorded here so reposts / cross-account duplicates are discarded for free.
create table if not exists public.processed_hashes (
    id              uuid primary key default gen_random_uuid(),
    md5_url         text not null unique,       -- first-stage: MD5 of image CDN URL
    sha256_binary   text unique,                -- second-stage: SHA-256 of fetched image bytes
    source_url      text,                       -- provenance of the originating post
    processed_at    timestamptz not null default now()
);

-- Constant-time membership lookups for both dedup stages.
create index if not exists processed_hashes_md5_url_idx
    on public.processed_hashes (md5_url);

create index if not exists processed_hashes_sha256_binary_idx
    on public.processed_hashes (sha256_binary);

-- processed_hashes holds no user-owned data and is written exclusively by the
-- backend service role; RLS is enabled with no public policies so anon/auth
-- clients cannot read or write it.
alter table public.processed_hashes enable row level security;

-- -----------------------------------------------------------------------------
-- 2. user_tokens — OAuth 2.0 credential persistence (Stage 03)
-- -----------------------------------------------------------------------------
-- Stores access/refresh tokens obtained via the Authorization Code Flow with
-- PKCE. One row per (user, provider). The calendar tool node retrieves the
-- owning user's token to call events.insert() / Microsoft Graph POST /me/events.
create table if not exists public.user_tokens (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references auth.users (id) on delete cascade,
    provider        text not null,              -- 'google' | 'microsoft'
    access_token    text not null,
    refresh_token   text,
    scope           text,
    token_type      text,
    expires_at      timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    unique (user_id, provider)
);

create index if not exists user_tokens_user_id_idx
    on public.user_tokens (user_id);

-- Keep updated_at current on every refresh / re-auth.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists user_tokens_set_updated_at on public.user_tokens;
create trigger user_tokens_set_updated_at
    before update on public.user_tokens
    for each row
    execute function public.set_updated_at();

-- Row-level security: a token row is accessible only to its owning user.
-- (proposal §4.2: "Supabase row-level security policies ensure user_tokens
--  rows are accessible only to their owning authenticated user.")
alter table public.user_tokens enable row level security;

drop policy if exists user_tokens_select_own on public.user_tokens;
create policy user_tokens_select_own
    on public.user_tokens
    for select
    using (auth.uid() = user_id);

drop policy if exists user_tokens_modify_own on public.user_tokens;
create policy user_tokens_modify_own
    on public.user_tokens
    for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);
