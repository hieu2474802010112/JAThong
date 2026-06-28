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
