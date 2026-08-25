-- ============================================================
-- 0007_create_feedback.sql
-- v0.7.0 — Feedback agent + export
-- Creates the `feedback` table for JuryAI.
-- Run this in the Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

-- One CURRENT feedback row per submission, written by the Groq-powered
-- FeedbackAgent from the four criterion scores + their justifications:
--   strengths   — what the team did well (evidence-citing bullets)
--   weaknesses  — where the submission falls short
--   suggestion  — exactly ONE actionable improvement
--   verdict     — "shortlist" | "reject" (accept/reject framing)
-- Regenerating feedback UPSERTS this row so it always reflects the
-- latest scores (scores themselves stay append-only history).
create table if not exists public.feedback (
    id            uuid primary key default gen_random_uuid(),
    submission_id uuid not null unique references public.submissions (id) on delete cascade,
    strengths     jsonb not null,
    weaknesses    jsonb not null,
    suggestion    text not null,
    verdict       text not null check (verdict in ('shortlist', 'reject')),
    agent_version text not null,
    generated_at  timestamptz not null default now()
);

-- Index for looking up the feedback row for a given submission.
create index if not exists idx_feedback_submission_id
    on public.feedback (submission_id);

-- Enable Row Level Security (RLS) on the table.
-- v0.7.0 has no auth; allow anonymous reads/writes for now,
-- matching the 0003/0006 pattern.
-- NOTE: tighten this once auth is introduced (v1.x).
alter table public.feedback enable row level security;

create policy "allow_anon_select_feedback"
    on public.feedback
    for select
    to anon
    using (true);

create policy "allow_anon_insert_feedback"
    on public.feedback
    for insert
    to anon
    with check (true);

create policy "allow_anon_update_feedback"
    on public.feedback
    for update
    to anon
    using (true)
    with check (true);
