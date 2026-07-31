-- =============================================================================
-- Club & Event Concierge — Application user accounts
-- Migration: 20260703000000_app_users.sql
--
-- First-party account store for the demo application. Passwords are held only
-- as salted PBKDF2-SHA256 hashes (hashing happens in the backend); rows are
-- reachable exclusively through the backend service connection — RLS is
-- enabled with no public policies, so anon/authenticated Supabase clients
-- cannot read or write this table.
-- =============================================================================

create table if not exists public.app_users (
    id              uuid primary key default gen_random_uuid(),
    email           text not null unique,
    name            text not null,
    password_hash   text not null,              -- pbkdf2$<iters>$<salt-hex>$<hash-hex>
    campus          text,                       -- 'UBC' | 'SFU' | 'BCIT' | 'Douglas'
    program         text,
    interests       text[] not null default '{}',
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists app_users_email_idx on public.app_users (lower(email));

-- Keep updated_at current (function created in the dedup/tokens migration).
drop trigger if exists app_users_set_updated_at on public.app_users;
create trigger app_users_set_updated_at
    before update on public.app_users
    for each row
    execute function public.set_updated_at();

-- Private by default: no policies -> only the service connection can touch it.
alter table public.app_users enable row level security;
