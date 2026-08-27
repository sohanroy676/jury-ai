-- ============================================================
-- 0011_create_hackathon_settings.sql
-- v1.3.0 — Appeal flow: "results published" gate.
-- Introduces the (previously missing) hackathon entity. For the appeal
-- flow, results_published_at is the explicit operator-controlled switch
-- that unlocks the team appeal form; it also seeds the hackathon/deadline
-- data model that deadline reminders (ROADMAP "Next") will build on.
--
-- Apply in Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

create table if not exists public.hackathon_settings (
    hackathon_id         text primary key default 'default',
    results_published_at timestamptz,
    updated_at           timestamptz not null default now()
);

-- Seed the single default hackathon with RESULTS CLOSED
-- (results_published_at NULL). The evaluator flips this via the API.
insert into public.hackathon_settings (hackathon_id)
values ('default')
on conflict (hackathon_id) do nothing;

-- RLS matches the v0.x convention (no auth yet — tighten once auth lands).
alter table public.hackathon_settings enable row level security;

create policy "allow_anon_select_hackathon_settings"
    on public.hackathon_settings
    for select
    to anon
    using (true);

create policy "allow_anon_update_hackathon_settings"
    on public.hackathon_settings
    for update
    to anon
    using (true)
    with check (true);
