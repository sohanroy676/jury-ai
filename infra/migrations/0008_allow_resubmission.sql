-- ============================================================
-- 0008_allow_resubmission.sql
-- v1.1.0 — Submission UX: allow teams to re-submit their deck.
-- A re-submission ARCHIVES the team's previous active submission by
-- stamping superseded_at; NULL superseded_at means the row is active.
-- History is preserved: superseded rows remain queryable by id and
-- are excluded from listings/leaderboards/batch scoring.
--
-- Apply in Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

alter table public.submissions
    add column if not exists superseded_at timestamptz;

-- Fast case-insensitive lookup of a team's ACTIVE submission
-- (used by the re-submission conflict gate on every upload).
create index if not exists idx_submissions_team_active
    on public.submissions (lower(team_name))
    where superseded_at is null;
