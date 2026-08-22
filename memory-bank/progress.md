# Progress

<!-- Running log. Append, don't rewrite history. Newest at top.
     This tracks WORK STATUS (agent-facing, session to session).
     For the forward-looking feature plan, see ROADMAP.md instead —
     don't duplicate the full plan here, just what's actually in motion. -->

## Done

- v0.3.0 — Single scoring agent: Groq-powered (llama-3.3-70b-versatile), hardcoded 4-criteria rubric (problem_fit, technical_depth, feasibility, innovation), structured JSON score output with retry/backoff for rate limits and malformed JSON recovery. Adds `agents/scoring/scorer.py`, `infra/migrations/0003_create_scores.sql`, `POST /api/submissions/{id}/score` endpoint, `get_parsed_submission` and `insert_scores` Supabase service functions. Tests: 38 total (12 new scoring tests + 26 existing) pass; ruff clean. Committed on `feature/v0.3.0-scoring-agent` (commit `51e7fef`), not yet merged to `main`. — 2026-08-22
- v0.2.0 — Parsing agent: extract structured text from PDF (PyMuPDF) and PPTX (python-pptx), chunk into sections, stored in a `parsed_submissions` table. Implemented and merged: committed directly on `main` as `ea558e7` (linear history — the earlier `feature/v0.2.0-parsing` note was inaccurate; no separate branch, no merge commit), followed by memory-bank docs commit `96fda45`. Adds `agents/parsing/extractor.py`, `infra/migrations/0002_create_parsed_submissions.sql`, `insert_parsed_submission` service, and parse-on-upload wiring in `POST /api/submissions`. Tests: 21 total (11 backend + 10 agents) pass; ruff clean. Local `main` in sync with `origin/main`. — 2026-08-21
- v0.1.0 — Project skeleton: Next.js upload portal, FastAPI backend with `/api/submissions` upload endpoint, Supabase Postgres + Storage wiring, SQL migration for `submissions` table, `.env.example` + `docs/setup.md` Supabase guide. Backend tests (8) + frontend tests (3) pass; ruff + eslint + prettier clean. — 2026-08-20
- CORS fix — Added `CORSMiddleware` to the FastAPI app (origins from `FRONTEND_URL` env var, default `http://localhost:3000`). Resolved the "Network error — could not reach the backend" issue in the upload portal. Merged into `main` (commit `6179319` + formatting fix `25537c4`). Backend tests now 10, all pass. — 2026-08-21

## In progress

- (none — v0.3.0 committed on `feature/v0.3.0-scoring-agent`; next is v0.4.0 checkpoint)
