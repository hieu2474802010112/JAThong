-- ============================================================
-- Portfolio Builder v2 — Supabase Trigger Migration
-- Runs this in the Supabase SQL Editor
-- ============================================================

-- 1. Ensure the portfolio_sessions table exists (idempotent)
create table if not exists public.portfolio_sessions (
    id          uuid primary key default gen_random_uuid(),
    state       text not null default 'collect_name',
    data        jsonb not null default '{}'::jsonb,
    completed   boolean not null default false,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

alter table public.portfolio_sessions enable row level security;

-- Allow open access for MVP (no auth required on portfolio builder)
do $$ begin
  if not exists (
    select 1 from pg_policies
    where tablename = 'portfolio_sessions'
    and policyname  = 'Allow all on portfolio_sessions'
  ) then
    execute 'create policy "Allow all on portfolio_sessions"
      on public.portfolio_sessions for all
      using (true) with check (true)';
  end if;
end $$;

-- ============================================================
-- 2. updated_at auto-stamp trigger
-- ============================================================
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists portfolio_sessions_updated_at on public.portfolio_sessions;
create trigger portfolio_sessions_updated_at
  before update on public.portfolio_sessions
  for each row execute function public.set_updated_at();

-- ============================================================
-- 3. Auto-sync to candidates when completed flips to TRUE
-- ============================================================
create or replace function public.sync_portfolio_to_candidates()
returns trigger language plpgsql security definer as $$
declare
  v_full_name text;
  v_email     text;
begin
  -- Only fire when completed transitions false → true
  if (old.completed = false and new.completed = true) then
    v_full_name := coalesce(new.data->>'full_name', 'Không rõ');
    v_email     := coalesce(new.data->>'email',     'portfolio@jathong.ai');

    -- UPSERT: update existing row if same email exists, otherwise insert
    insert into public.candidates (full_name, email, metadata)
    values (v_full_name, v_email, new.data)
    on conflict (email) do update
      set full_name = excluded.full_name,
          metadata  = public.candidates.metadata || excluded.metadata,
          updated_at = now();
  end if;
  return new;
end;
$$;

drop trigger if exists on_portfolio_completed on public.portfolio_sessions;
create trigger on_portfolio_completed
  after update on public.portfolio_sessions
  for each row execute function public.sync_portfolio_to_candidates();

-- ============================================================
-- 4. Add unique constraint on candidates.email (required for UPSERT)
--    Run only if it doesn't already exist
-- ============================================================
do $$ begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'candidates_email_key'
    and conrelid  = 'public.candidates'::regclass
  ) then
    alter table public.candidates add constraint candidates_email_key unique (email);
  end if;
end $$;
