-- ============================================================
-- 0013_multi_track_support.sql
-- v3.1.0 — Multi-track support + v3.2.0 analytics scaffolding
-- Adds hackathon_id scoping to all tables and creates the tracks table.
-- Run this in the Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

-- Tracks table: one row per track/hackathon
create table if not exists public.tracks (
    id          text primary key,           -- slug like 'sih-2026'
    name        text not null,              -- display name
    description text,
    created_at  timestamptz not null default now()
);

-- Seed default track
insert into public.tracks (id, name, description)
values ('default', 'Default track', 'Built-in track for unscoped submissions')
on conflict (id) do nothing;

-- Add hackathon_id to submissions (backfill existing as 'default')
alter table public.submissions
    add column if not exists hackathon_id text not null default 'default'
    references public.tracks(id) on delete restrict;
create index if not exists idx_submissions_hackathon
    on public.submissions(hackathon_id);

-- Add hackathon_id to parsed_submissions
alter table public.parsed_submissions
    add column if not exists hackathon_id text not null default 'default';
create index if not exists idx_parsed_hackathon
    on public.parsed_submissions(hackathon_id);

-- Add hackathon_id to scores
alter table public.scores
    add column if not exists hackathon_id text not null default 'default';
create index if not exists idx_scores_hackathon
    on public.scores(hackathon_id);

-- Add hackathon_id to feedback
alter table public.feedback
    add column if not exists hackathon_id text not null default 'default';
create index if not exists idx_feedback_hackathon
    on public.feedback(hackathon_id);

-- Add hackathon_id to appeals
alter table public.appeals
    add column if not exists hackathon_id text not null default 'default';
create index if not exists idx_appeals_hackathon
    on public.appeals(hackathon_id);

-- RLS on tracks
alter table public.tracks enable row level security;

create policy "allow_anon_select_tracks"
    on public.tracks for select to anon using (true);

create policy "allow_anon_insert_tracks"
    on public.tracks for insert to anon with check (true);

create policy "allow_anon_delete_tracks"
    on public.tracks for delete to anon using (true);
