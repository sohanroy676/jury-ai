-- ============================================================
-- 0012_create_appeals.sql
-- v1.3.0 — Appeal flow
-- Creates the `appeals` table for JuryAI.
-- Run this in the Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

-- One live appeal per submission (unique). Teams may contest a result
-- only AFTER feedback exists (results published). The evaluator works
-- through a queue and logs a final decision on the row.
create table if not exists public.appeals (
    id             uuid primary key default gen_random_uuid(),
    submission_id  uuid not null unique references public.submissions (id) on delete cascade,
    appeal_text    text not null check (char_length(appeal_text) >= 50),
    status         text not null default 'pending'
                   check (status in ('pending', 'under_review', 'upheld', 'overturned')),
    evaluator_notes text,
    resolved_by    text,
    created_at     timestamptz not null default now(),
    resolved_at    timestamptz
);

-- Evaluator queue: fetch by status ordered oldest-first.
create index if not exists idx_appeals_status_created
    on public.appeals (status, created_at);

-- Team-facing lookup: one live appeal per submission (unique already).
create index if not exists idx_appeals_submission_id
    on public.appeals (submission_id);

-- RLS: no auth yet; allow anonymous reads/writes, matching 0003/0007.
alter table public.appeals enable row level security;

create policy "allow_anon_select_appeals"
    on public.appeals
    for select
    to anon
    using (true);

create policy "allow_anon_insert_appeals"
    on public.appeals
    for insert
    to anon
    with check (true);

create policy "allow_anon_update_appeals"
    on public.appeals
    for update
    to anon
    using (true)
    with check (true);