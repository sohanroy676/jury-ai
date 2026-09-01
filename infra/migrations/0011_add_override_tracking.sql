-- ============================================================
-- 0011_add_override_tracking.sql
-- v2.1.0 — Evaluator score overrides
-- Adds override provenance columns to the `scores` table.
-- Run this in the Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

-- An override edits the LIVE score row in place (ranking always reads
-- current scores), but preserves who changed it, when, why, and — on
-- the FIRST override only — what the AI originally said, so the
-- original judgment is never lost (v2.2.0's audit trail builds on
-- these columns).
alter table public.scores
    add column if not exists original_score int,
    add column if not exists overridden_at timestamptz,
    add column if not exists overridden_by text,
    add column if not exists override_reason text;

-- Evaluator dashboard: quick scan for rows a human has adjusted.
create index if not exists idx_scores_overridden
    on public.scores (submission_id)
    where overridden_at is not null;

-- Policy: allow anonymous updates (evaluator override endpoint).
create policy "allow_anon_update_scores"
    on public.scores
    for update
    to anon
    using (true)
    with check (true);