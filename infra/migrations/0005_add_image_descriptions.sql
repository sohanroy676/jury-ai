-- ============================================================
-- 0005_add_image_descriptions.sql
-- v0.3.5 — Visual content understanding
-- Adds the `image_descriptions` column to `parsed_submissions`.
-- Run this in the Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

-- Stores the vision-LLM descriptions of embedded images extracted
-- from each submission, keyed by page/slide number. Each entry looks
-- like:
--   {
--     "page": 3,
--     "phash": "e0f1c2...",
--     "classification": "architecture diagram",
--     "confidence": 0.91,
--     "description": "Three-tier architecture with ...",
--     "needs_human_review": false
--   }
alter table public.parsed_submissions
    add column if not exists image_descriptions jsonb not null default '[]'::jsonb;