# Progress

<!-- Running log. Append, don't rewrite history. Newest at top.
     This tracks WORK STATUS (agent-facing, session to session).
     For the forward-looking feature plan, see ROADMAP.md instead —
     don't duplicate the full plan here, just what's actually in motion. -->

## Done

- Unicode dash normalization fix — PDF/PPTX generators emit typographic dash variants (U+2010-U+2014, U+2212) that PyMuPDF/python-pptx extract verbatim and the LLM echoes into justifications. Added `normalize_unicode_dashes()` in the parsing agent (applied to all extracted PDF/PPTX text) and applied it to LLM justifications in the scoring agent. Also switched the scoring model from `llama-3.3-70b-versatile` (removed from Groq free tier, 404) to `openai/gpt-oss-120b` (roadmap alternative). Groq verified working end-to-end against a real submission. Tests: 41 total pass; ruff clean. Commits `869aaf7` (model fix) and `d5172bf` (dash normalization) on `feature/v0.3.0-scoring-agent`. — 2026-08-22
- v0.3.0 — Single scoring agent: Groq-powered, hardcoded 4-criteria rubric (problem_fit, technical_depth, feasibility, innovation), structured JSON score output with retry/backoff for rate limits and malformed JSON recovery. Adds `agents/scoring/scorer.py`, `infra/migrations/0003_create_scores.sql`, `POST /api/submissions/{id}/score` endpoint, `get_parsed_submission` and `insert_scores` Supabase service functions. Committed on `feature/v0.3.0-scoring-agent` (commit `51e7fef`), not yet merged to `main`. — 2026-08-22
- v0.2.0 — Parsing agent: extract structured text from PDF (PyMuPDF) and PPTX (python-pptx), chunk into sections, stored in a `parsed_submissions` table. Implemented and merged: committed directly on `main` as `ea558e7` (linear history — the earlier `feature/v0.2.0-parsing` note was inaccurate; no separate branch, no merge commit), followed by memory-bank docs commit `96fda45`. Adds `agents/parsing/extractor.py`, `infra/migrations/0002_create_parsed_submissions.sql`, `insert_parsed_submission` service, and parse-on-upload wiring in `POST /api/submissions`. Tests: 21 total (11 backend + 10 agents) pass; ruff clean. Local `main` in sync with `origin/main`. — 2026-08-21
- v0.1.0 — Project skeleton: Next.js upload portal, FastAPI backend with `/api/submissions` upload endpoint, Supabase Postgres + Storage wiring, SQL migration for `submissions` table, `.env.example` + `docs/setup.md` Supabase guide. Backend tests (8) + frontend tests (3) pass; ruff + eslint + prettier clean. — 2026-08-20
- CORS fix — Added `CORSMiddleware` to the FastAPI app (origins from `FRONTEND_URL` env var, default `http://localhost:3000`). Resolved the "Network error — could not reach the backend" issue in the upload portal. Merged into `main` (commit `6179319` + formatting fix `25537c4`). Backend tests now 10, all pass. — 2026-08-21

## In progress

- (none — v0.3.5 merged to main; awaiting user's TPD-reset verification before tagging)

## Done

- v0.3.5 — Visual content understanding: implemented on `feature/v0.3.5-image-understanding` (`0292b7f` pipeline, `a85e92c` scoring merge, `d8e063d`/`53273b8` docs), migrations 0004/0005 applied by user, then LIVE E2E verified against real files: Clarix.pptx fully green (10 clean image descriptions, structural filter excluded layout art, low-confidence flags, cross-submission cache ~14x faster on duplicate upload, scoring with diagram-informed justifications); scango.pdf exposed Groq qwen3.6 free-tier **200k tokens-per-DAY cap** — post-exhaustion vision calls 429 and images degrade to `description: null` + `needs_human_review: true` (by design, uncached/retryable). Fixes from live testing: unterminated qwen reasoning blocks stripped + MAX_TOKENS 2048 (`40e21e8`); `get_parsed_submission` PGRST116 500 on missing rows -> limit(1)+None clean 404 (`b6e4097`); rate-limit circuit breaker stops doomed calls mid-run (`89daf5b`). **Merged to `main` and pushed 2026-08-23 — NOT yet tagged**: tag `v0.3.5` after user re-uploads scango.pdf post-TPD-reset and confirms diagrams land in image_cache. Tests: 105 pass; ruff clean. — 2026-08-23
