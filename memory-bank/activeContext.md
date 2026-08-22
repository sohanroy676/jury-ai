# Active Context

<!-- Update this at the end of every session. This is the first thing to read when resuming. -->

## Current focus
v0.3.0 (single scoring agent) is implemented, tested (38/38 pass), and committed on `feature/v0.3.0-scoring-agent` (commit `51e7fef`), not yet merged to `main`. v0.1.0 and v0.2.0 are merged into `main` and in sync with `origin/main`. Next up is v0.4.0 (core loop checkpoint).

## Recent decisions
- Chose FastAPI + Supabase (Postgres + Storage) for v0.1.0, matching the established tech-stack. No local SQLite fallback — real Supabase keys will be added.
- Backend upload endpoint: `POST /api/submissions` validates file type (.pdf/.pptx) and size (50 MB), uploads to Supabase Storage, inserts a `submissions` row.
- Frontend: minimal Next.js upload portal with client-side file-type validation.
- Pinned `pydantic==2.12.4` (not 2.10.4) because 2.10.4's `pydantic-core` has no Python 3.14 wheel and fails to build on this machine.
- Pinned `httpx==0.27.2` (not 0.28.1) to satisfy `supabase==2.9.0`'s `httpx<0.28` constraint.
- Upgraded `next` to `15.5.23` (patched CVE-2025-66478) and `eslint`/`vitest` to patched versions. Remaining `npm audit` items (postcss/sharp) only resolve via a breaking Next 16 upgrade — deferred.
- **CORS fix (merged into main):** Added `CORSMiddleware` to the FastAPI app. Allowed origins come from the `FRONTEND_URL` env var (comma-separated, defaults to `http://localhost:3000`). Methods: GET/POST/OPTIONS; headers: Content-Type; credentials allowed. This resolved the "Network error — could not reach the backend" issue in the upload portal.
- **v0.3.0 scoring agent:** Single Groq-powered agent with hardcoded 4-criteria rubric (problem_fit, technical_depth, feasibility, innovation), JSON response format enforcement, retry/backoff for rate limits (429) and malformed JSON recovery. `POST /api/submissions/{id}/score` endpoint fetches parsed text, scores, and stores results in `scores` table. `GROQ_API_KEY` added to `.env.example` and `backend/config.py`. Committed on `feature/v0.3.0-scoring-agent` (commit `51e7fef`).

## Blockers / open questions
- v0.3.0 is committed on `feature/v0.3.0-scoring-agent` but not yet merged to `main` — needs review/merge.
- Remaining frontend `npm audit` vulnerabilities (postcss, sharp) require a breaking Next 16 upgrade — decide whether to do this later.

## Next step
- v0.4.0 checkpoint: verify the full core loop (upload → parse → score) works end to end. All migrations (`0001`, `0002`, `0003`) have been run in Supabase and `GROQ_API_KEY` is in `.env`. Test `POST /api/submissions/{id}/score` against a real submission, then merge `feature/v0.3.0-scoring-agent` into `main`.
