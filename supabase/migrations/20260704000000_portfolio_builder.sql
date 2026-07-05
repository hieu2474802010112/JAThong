-- ============================================================
-- Portfolio Builder tables migration
-- ============================================================

-- Portfolio sessions: one per anonymous/identified user flow
create table if not exists public.portfolio_sessions (
    id          uuid primary key default gen_random_uuid(),
    state       text not null default 'collect_name',  -- current FSM state
    data        jsonb not null default '{}'::jsonb,    -- accumulated answers
    completed   boolean not null default false,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- Allow unrestricted access for MVP (no auth required on portfolio builder)
alter table public.portfolio_sessions enable row level security;

create policy "Allow all on portfolio_sessions"
    on public.portfolio_sessions for all
    using (true)
    with check (true);
