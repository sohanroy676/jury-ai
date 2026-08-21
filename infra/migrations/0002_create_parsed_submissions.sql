-- ============================================================
-- 0002_create_parsed_submissions.sql
-- v0.2.0 — Parsing agent
-- Creates the `parsed_submissions` table for JuryAI.
-- Run this in the Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

-- The `parsed_submissions` table stores the structured text extracted
-- from each uploaded submission by the parsing agent.
create table if not exists public.parsed_submissions (
    id            uuid primary key default gen_random_uuid(),
    submission_id uuid not null references public.submissions (id) on delete cascade,
    raw_text      text not null,
    sections      jsonb not null default '[]'::jsonb,
    source_format text not null check (source_format in ('pdf', 'pptx')),
    parsed_at     timestamptz not null default now()
);

-- One parsed row per submission.
create unique index if not exists idx_parsed_submissions_submission_id
    on public.parsed_submissions (submission_id);

-- Enable Row Level Security (RLS) on the table.
-- v0.2.0 has no auth, so we allow public read/write for now.
-- NOTE: tighten this once auth is introduced (v1.x).
alter table public.parsed_submissions enable row level security;

-- Policy: allow anonymous inserts (parsing agent writes parsed output).
create policy "allow_anon_insert_parsed_submissions"
    on public.parsed_submissions
    for insert
    to anon
    with check (true);

-- Policy: allow anonymous reads (evaluator dashboard / status view).
create policy "allow_anon_select_parsed_submissions"
    on public.parsed_submissions
    for select
    to anon
    using (true);