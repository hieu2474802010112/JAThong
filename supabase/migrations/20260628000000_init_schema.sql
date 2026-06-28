-- Enable UUID generation extension
create extension if not exists "uuid-ossp";

-- =========================================================================
-- 1. TABLES DEFINITIONS
-- =========================================================================

-- Public Users table (mirrors and extends auth.users)
create table public.users (
    id uuid references auth.users on delete cascade primary key,
    email text not null unique,
    full_name text,
    role text default 'candidate' check (role in ('admin', 'recruiter', 'candidate')),
    created_at timestamp with time zone default timezone('utc'::text, now()) not null,
    updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Candidates table
create table public.candidates (
    id uuid default gen_random_uuid() primary key,
    user_id uuid references public.users(id) on delete set null,
    full_name text not null,
    email text not null,
    phone text,
    skills text[],
    experience_years numeric,
    education text,
    metadata jsonb default '{}'::jsonb not null,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null,
    updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- CV Records table
create table public.cv_records (
    id uuid default gen_random_uuid() primary key,
    candidate_id uuid references public.candidates(id) on delete cascade not null,
    file_path text not null, -- Path inside Supabase Storage bucket
    file_name text not null,
    file_size integer not null,
    parsed_text text, -- Extracted text using PyMuPDF
    status text default 'pending' check (status in ('pending', 'parsing', 'parsed', 'failed')),
    created_by uuid references public.users(id) on delete set null,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null,
    updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- AI Evaluations table
create table public.ai_evaluations (
    id uuid default gen_random_uuid() primary key,
    cv_record_id uuid references public.cv_records(id) on delete cascade unique not null,
    overall_score integer check (overall_score >= 0 and overall_score <= 100) not null,
    suitability_summary text,
    strengths text[],
    weaknesses text[],
    technical_skills_evaluation jsonb not null default '{}'::jsonb,
    experience_evaluation text,
    recommendations text,
    raw_ai_response jsonb,
    evaluated_by uuid references public.users(id) on delete set null,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Chat Sessions table
create table public.chat_sessions (
    id uuid default gen_random_uuid() primary key,
    cv_record_id uuid references public.cv_records(id) on delete cascade not null,
    user_id uuid references public.users(id) on delete cascade not null,
    title text default 'Chat về ứng viên' not null,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Chat Messages table
create table public.chat_messages (
    id uuid default gen_random_uuid() primary key,
    session_id uuid references public.chat_sessions(id) on delete cascade not null,
    sender text not null check (sender in ('user', 'assistant')),
    content text not null,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- =========================================================================
-- 2. AUTOMATIC USER SYNC TRIGGER
-- =========================================================================

-- Trigger function to automatically insert new auth user into public.users
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.users (id, email, full_name, role)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'full_name', ''),
    coalesce(new.raw_user_meta_data->>'role', 'candidate')
  );
  return new;
end;
$$ language plpgsql security definer;

-- Bind the trigger to auth.users
create or replace trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- =========================================================================
-- 3. ROW LEVEL SECURITY (RLS) POLICIES
-- =========================================================================

-- Enable RLS on all tables
alter table public.users enable row level security;
alter table public.candidates enable row level security;
alter table public.cv_records enable row level security;
alter table public.ai_evaluations enable row level security;
alter table public.chat_sessions enable row level security;
alter table public.chat_messages enable row level security;

-- --- 3.1 Users Policies ---
create policy "Users can view their own profile or admins/recruiters can view all"
    on public.users for select
    using (auth.uid() = id or (select role from public.users where id = auth.uid()) in ('admin', 'recruiter'));

create policy "Users can update their own profile"
    on public.users for update
    using (auth.uid() = id);

-- --- 3.2 Candidates Policies ---
create policy "Admins and Recruiters have full access to Candidates"
    on public.candidates for all
    using ((select role from public.users where id = auth.uid()) in ('admin', 'recruiter'));

create policy "Candidates can view their own candidate record"
    on public.candidates for select
    using (user_id = auth.uid());

-- --- 3.3 CV Records Policies ---
create policy "Admins and Recruiters have full access to CV Records"
    on public.cv_records for all
    using ((select role from public.users where id = auth.uid()) in ('admin', 'recruiter'));

create policy "Candidates can view their own CV records"
    on public.cv_records for select
    using (exists (
        select 1 from public.candidates 
        where id = cv_records.candidate_id and user_id = auth.uid()
    ));

-- --- 3.4 AI Evaluations Policies ---
create policy "Admins and Recruiters have full access to AI Evaluations"
    on public.ai_evaluations for all
    using ((select role from public.users where id = auth.uid()) in ('admin', 'recruiter'));

create policy "Candidates can view their own AI Evaluations"
    on public.ai_evaluations for select
    using (exists (
        select 1 from public.cv_records
        join public.candidates on cv_records.candidate_id = candidates.id
        where cv_records.id = ai_evaluations.cv_record_id and candidates.user_id = auth.uid()
    ));

-- --- 3.5 Chat Sessions Policies ---
create policy "Users can manage their own chat sessions"
    on public.chat_sessions for all
    using (user_id = auth.uid() or (select role from public.users where id = auth.uid()) in ('admin', 'recruiter'));

-- --- 3.6 Chat Messages Policies ---
create policy "Users can manage messages in their own chat sessions"
    on public.chat_messages for all
    using (exists (
        select 1 from public.chat_sessions
        where id = chat_messages.session_id and (user_id = auth.uid() or (select role from public.users where id = auth.uid()) in ('admin', 'recruiter'))
    ));

-- =========================================================================
-- 4. AUTOMATIC STORAGE BUCKET INITIALIZATION & POLICIES
-- =========================================================================

-- Create public bucket 'cv-records' if it does not exist
insert into storage.buckets (id, name, public)
values ('cv-records', 'cv-records', true)
on conflict (id) do nothing;

-- Ensure RLS is enabled on storage.objects
alter table storage.objects enable row level security;

-- Policy to allow public read access on cv-records bucket
create policy "Allow public read access to cv-records"
on storage.objects for select
using (bucket_id = 'cv-records');

-- Policy to allow authenticated uploads to cv-records bucket
create policy "Allow authenticated uploads to cv-records"
on storage.objects for insert
with check (bucket_id = 'cv-records' and auth.role() = 'authenticated');

