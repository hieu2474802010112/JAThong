-- ============================================================
-- Migration: chatbot_sessions & support_requests
-- ============================================================

-- Create chatbot_sessions table
create table if not exists public.chatbot_sessions (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid references public.users(id) on delete set null,
    current_state text not null default 'INIT' check (current_state in ('INIT', 'EXPLORING', 'DONE')),
    -- Additional fields to store FSM substate and data
    state         text not null default 'collect_name',
    data          jsonb not null default '{}'::jsonb,
    completed     boolean not null default false,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

-- Create support_requests table
create table if not exists public.support_requests (
    id         uuid primary key default gen_random_uuid(),
    session_id uuid references public.chatbot_sessions(id) on delete cascade unique,
    status     text not null default 'PENDING' check (status in ('PENDING', 'PROCESSED')),
    created_at timestamptz not null default now()
);

-- Enable RLS and add policies
alter table public.chatbot_sessions enable row level security;
alter table public.support_requests enable row level security;

-- Policy to allow all operations for simplicity in this MVP
do $$ begin
  if not exists (
    select 1 from pg_policies where tablename = 'chatbot_sessions' and policyname = 'Allow all on chatbot_sessions'
  ) then
    create policy "Allow all on chatbot_sessions" on public.chatbot_sessions for all using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where tablename = 'support_requests' and policyname = 'Allow all on support_requests'
  ) then
    create policy "Allow all on support_requests" on public.support_requests for all using (true) with check (true);
  end if;
end $$;

-- Drop trigger on portfolio_sessions if it exists
drop trigger if exists on_portfolio_completed on public.portfolio_sessions;

-- Sync to candidates when completed is set to true on chatbot_sessions
create or replace function public.sync_chatbot_completed_to_candidates()
returns trigger language plpgsql security definer as $$
declare
  v_full_name text;
  v_email     text;
begin
  if (old.completed = false and new.completed = true) or (old.current_state <> 'DONE' and new.current_state = 'DONE') then
    v_full_name := coalesce(new.data->>'full_name', 'Không rõ');
    v_email     := coalesce(new.data->>'email',     'portfolio@jathong.ai');

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

drop trigger if exists on_chatbot_completed on public.chatbot_sessions;
create trigger on_chatbot_completed
  after update on public.chatbot_sessions
  for each row execute function public.sync_chatbot_completed_to_candidates();
