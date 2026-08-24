-- ============================================================
-- 0006_create_rubric_config.sql
-- v0.6.0 — Weighted scoring + ranking
-- Creates the `rubric_config` table for JuryAI.
-- Run this in the Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

-- Per-hackathon criterion weights used by the ranking engine:
--   composite_score = sum(criterion_score * weight)
-- Weights are fractions (0..1) and must sum to ~1.0 across the four
-- criteria; validation is enforced in the API layer (PUT /api/rubrics).
create table if not exists public.rubric_config (
    id            uuid primary key default gen_random_uuid(),
    hackathon_id  text not null default 'default',
    criterion     text not null check (criterion in ('problem_fit', 'technical_depth', 'feasibility', 'innovation')),
    weight        double precision not null check (weight >= 0 and weight <= 1),
    updated_at    timestamptz not null default now(),
    unique (hackathon_id, criterion)
);

-- Seed the built-in 'default' hackathon with an equal-weight rubric
-- (25% per criterion). Idempotent: re-running changes nothing.
insert into public.rubric_config (hackathon_id, criterion, weight)
values
    ('default', 'problem_fit',      0.25),
    ('default', 'technical_depth',  0.25),
    ('default', 'feasibility',      0.25),
    ('default', 'innovation',       0.25)
on conflict (hackathon_id, criterion) do nothing;

-- Enable Row Level Security (RLS) on the table.
-- v0.6.0 has no auth; allow anonymous reads/writes for now.
-- NOTE: tighten this once auth is introduced (v1.x), matching 0003.
alter table public.rubric_config enable row level security;

create policy "allow_anon_select_rubric"
    on public.rubric_config
    for select
    to anon
    using (true);

create policy "allow_anon_insert_rubric"
    on public.rubric_config
    for insert
    to anon
    with check (true);

create policy "allow_anon_update_rubric"
    on public.rubric_config
    for update
    to anon
    using (true)
    with check (true);