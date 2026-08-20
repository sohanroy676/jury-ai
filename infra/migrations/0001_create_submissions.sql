-- ============================================================
-- 0001_create_submissions.sql
-- v0.1.0 — Project skeleton
-- Creates the `submissions` table for JuryAI.
-- Run this in the Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

-- The `submissions` table stores one row per uploaded submission.
-- Status lifecycle (v0.1.0): only 'submitted' is used for now.
-- Later versions add: parsing, scored, shortlisted, rejected.
create table if not exists public.submissions (
    id          uuid primary key default gen_random_uuid(),
    team_name   text not null,
    file_url    text not null,
    file_type   text not null check (file_type in ('pdf', 'pptx')),
    status      text not null default 'submitted'
                check (status in ('submitted', 'parsing', 'scored', 'shortlisted', 'rejected')),
    uploaded_at timestamptz not null default now()
);

-- Index for listing submissions by upload time (used by later ranking/leaderboard).
create index if not exists idx_submissions_uploaded_at
    on public.submissions (uploaded_at desc);

-- Enable Row Level Security (RLS) on the table.
-- v0.1.0 has no auth, so we allow public read/write for now.
-- NOTE: tighten this once auth is introduced (v1.x).
alter table public.submissions enable row level security;

-- Policy: allow anonymous inserts (team uploads a submission).
create policy "allow_anon_insert_submissions"
    on public.submissions
    for insert
    to anon
    with check (true);

-- Policy: allow anonymous reads (evaluator dashboard / status view).
create policy "allow_anon_select_submissions"
    on public.submissions
    for select
    to anon
    using (true);