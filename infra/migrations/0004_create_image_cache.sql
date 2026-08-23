-- ============================================================
-- 0004_create_image_cache.sql
-- v0.3.5 — Visual content understanding
-- Creates the `image_cache` table for JuryAI.
-- Run this in the Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

-- The `image_cache` table stores CLIP classifications and vision-LLM
-- descriptions keyed by perceptual hash. Many teams reuse the same
-- hackathon template images (logos, banners, diagram styles), so each
-- unique image is classified and described only once across all
-- submissions.
create table if not exists public.image_cache (
    phash          text primary key,
    classification text not null,
    confidence     real,
    description    text,
    cached_at      timestamptz not null default now()
);

-- Enable Row Level Security (RLS) on the table.
-- v0.3.5 has no auth, so we allow public read/write for now.
-- NOTE: tighten this once auth is introduced (v1.x).
alter table public.image_cache enable row level security;

-- Policy: allow anonymous inserts (image pipeline writes cache entries).
create policy "allow_anon_insert_image_cache"
    on public.image_cache
    for insert
    to anon
    with check (true);

-- Policy: allow anonymous updates (the service layer upserts by phash,
-- which requires both INSERT and UPDATE privileges under RLS).
create policy "allow_anon_update_image_cache"
    on public.image_cache
    for update
    to anon
    using (true)
    with check (true);

-- Policy: allow anonymous reads (cache lookups before classification).
create policy "allow_anon_select_image_cache"
    on public.image_cache
    for select
    to anon
    using (true);