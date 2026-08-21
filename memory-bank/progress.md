# Progress

<!-- Running log. Append, don't rewrite history. Newest at top.
     This tracks WORK STATUS (agent-facing, session to session).
     For the forward-looking feature plan, see ROADMAP.md instead —
     don't duplicate the full plan here, just what's actually in motion. -->

## Done

- v0.2.0 — Parsing agent: extract structured text from PDF (PyMuPDF) and PPTX (python-pptx), chunk into sections, stored in a `parsed_submissions` table. Implemented on `feature/v0.2.0-parsing` (commit `ea558e7`), NOT yet merged to `main`. Adds `agents/parsing/extractor.py`, `infra/migrations/0002_create_parsed_submissions.sql`, `insert_parsed_submission` service, and parse-on-upload wiring. Tests: 21 total (11 backend + 10 agents) pass; ruff clean. — 2026-08-21
- v0.1.0 — Project skeleton: Next.js upload portal, FastAPI backend with `/api/submissions` upload endpoint, Supabase Postgres + Storage wiring, SQL migration for `submissions` table, `.env.example` + `docs/setup.md` Supabase guide. Backend tests (8) + frontend tests (3) pass; ruff + eslint + prettier clean. — 2026-08-20
- CORS fix — Added `CORSMiddleware` to the FastAPI app (origins from `FRONTEND_URL` env var, default `http://localhost:3000`). Resolved the "Network error — could not reach the backend" issue in the upload portal. Merged into `main` (commit `6179319` + formatting fix `25537c4`). Backend tests now 10, all pass. — 2026-08-21

## In progress

- (none — v0.2.0 committed on feature branch; next is v0.3.0 single scoring agent)
