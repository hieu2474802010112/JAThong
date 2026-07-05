-- ============================================================
-- Migration: support_requests Audit Log & pg_cron TTL
-- ============================================================

-- 1. Add audit columns to support_requests if not exist
alter table public.support_requests add column if not exists updated_by text;
alter table public.support_requests add column if not exists updated_at timestamp with time zone default now();

-- 2. Drop old status check constraint and add updated one including 'CONTACTED'
alter table public.support_requests drop constraint if exists support_requests_status_check;
alter table public.support_requests add constraint support_requests_status_check check (status in ('PENDING', 'CONTACTED', 'PROCESSED'));

-- 3. Create or replace audit trigger on support_requests
create or replace function public.on_support_request_updated()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  -- If status transitioned to CONTACTED and updated_by is not set, default to 'system'
  if new.status = 'CONTACTED' and (new.updated_by is null or new.updated_by = '') then
    new.updated_by := 'system';
  end if;
  return new;
end;
$$;

drop trigger if exists support_requests_audit_trig on public.support_requests;
create trigger support_requests_audit_trig
  before update on public.support_requests
  for each row execute function public.on_support_request_updated();

-- 4. Create public RPC function to clean up stale chatbot sessions
--    This is called by both pg_cron and Python APScheduler.
create or replace function public.cleanup_chatbot_sessions()
returns void language plpgsql security definer as $$
begin
  delete from public.chatbot_sessions
  where current_state in ('INIT', 'EXPLORING')
    and updated_at < now() - interval '30 days';
end;
$$;

-- 5. Set up database-native pg_cron task if pg_cron extension is available
--    This cleans up stale sessions (INIT/EXPLORING > 30 days old) monthly.
create extension if not exists pg_cron;

select cron.schedule(
  'cleanup-stale-chatbot-sessions',
  '0 0 1 * *', -- 00:00 on the first day of each month
  $$
  select public.cleanup_chatbot_sessions();
  $$
);
