-- ============================================================
-- 0010_create_appeals.sql
-- v1.3.0 — Appeal flow: let teams contest a published result.
-- A team files an appeal against a scored, feedback-carrying submission;
-- it lands in a human-evaluator queue with the original AI scoring +
-- feedback attached; the evaluator logs a final decision (upheld |
-- dismissed) against the submission.
--
-- Apply in Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

create table if not exists public.appeals (
    id            uuid primary key default gen_random_uuid(),
    submission_id uuid not null references public.submissions (id) on delete cascade,
    hackathon_id  text not null default 'default',
    reason        text not null,
    contact_email text,
    status        text not null default 'open' check (status in ('open', 'resolved')),
    decision      text check (decision in ('upheld', 'dismissed')),
    decision_note text,
    evaluator     text,
    created_at    timestamptz not null default now(),
    decided_at    timestamptz
);

-- A submission may have at most ONE OPEN appeal at a time (anti-spam).
-- Once resolved the row stays as history and a team may file again.
-- This partial unique index backs the route's 409 conflict gate.
create unique index if not exists idx_appeals_one_open_per_submission
    on public.appeals (submission_id)
    where status = 'open';

-- Evaluator queue: show open appeals oldest-first; resolved history is
-- reachable per-submission via the FK.
create index if not exists idx_appeals_status_created
    on public.appeals (status, created_at);

-- RLS matches the v0.x convention (no auth yet — tighten once auth lands).
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
