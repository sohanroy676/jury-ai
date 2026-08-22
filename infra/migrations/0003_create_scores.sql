-- ============================================================
-- 0003_create_scores.sql
-- v0.3.0 — Single scoring agent
-- Creates the `scores` table for JuryAI.
-- Run this in the Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

-- The `scores` table stores one row per criterion score per submission.
-- Each submission gets 4 rows (one per criterion: problem_fit,
-- technical_depth, feasibility, innovation).
create table if not exists public.scores (
    id            uuid primary key default gen_random_uuid(),
    submission_id uuid not null references public.submissions (id) on delete cascade,
    criterion     text not null check (criterion in ('problem_fit', 'technical_depth', 'feasibility', 'innovation')),
    score         int not null check (score >= 1 and score <= 10),
    justification text not null,
    agent_version text not null,
    scored_at     timestamptz not null default now()
);

-- Index for looking up all scores for a given submission.
create index if not exists idx_scores_submission_id
    on public.scores (submission_id);

-- Enable Row Level Security (RLS) on the table.
-- v0.3.0 has no auth, so we allow public read/write for now.
-- NOTE: tighten this once auth is introduced (v1.x).
alter table public.scores enable row level security;

-- Policy: allow anonymous inserts (scoring agent writes scores).
create policy "allow_anon_insert_scores"
    on public.scores
    for insert
    to anon
    with check (true);

-- Policy: allow anonymous reads (evaluator dashboard / status view).
create policy "allow_anon_select_scores"
    on public.scores
    for select
    to anon
    using (true);
