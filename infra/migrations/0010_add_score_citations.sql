-- ============================================================
-- 0010_add_score_citations.sql
-- v2.3.0 — Explainability: cited excerpts for each score
-- Adds cited_excerpt column to scores table.
-- Run this in the Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

-- Add the cited_excerpt column to store the textual reference
-- each scoring agent used to justify its score.
alter table public.scores
    add column if not exists cited_excerpt text not null default '';

-- Backfill: existing rows keep empty string (no citation available).
-- New scoring runs will populate this column.
