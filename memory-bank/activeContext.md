# Active Context

<!-- Update this at the end of every session. This is the first thing to read when resuming. -->

## Current focus
v0.3.0 (single scoring agent) is **released**: implemented, tested (41/41 pass), verified end-to-end against a real submission, merged into `main` (fast-forward to `02ba841`), tagged `v0.3.0`, and pushed to GitHub (`origin/main` + tag in sync). Next up is v0.4.0 (core loop checkpoint).

## Recent decisions
- Chose FastAPI + Supabase (Postgres + Storage) for v0.1.0, matching the established tech-stack. No local SQLite fallback — real Supabase keys will be added.
- Backend upload endpoint: `POST /api/submissions` validates file type (.pdf/.pptx) and size (50 MB), uploads to Supabase Storage, inserts a `submissions` row.
- Frontend: minimal Next.js upload portal with client-side file-type validation.
- Pinned `pydantic==2.12.4` (not 2.10.4) because 2.10.4's `pydantic-core` has no Python 3.14 wheel and fails to build on this machine.
- Pinned `httpx==0.27.2` (not 0.28.1) to satisfy `supabase==2.9.0`'s `httpx<0.28` constraint.
- Upgraded `next` to `15.5.23` (patched CVE-2025-66478) and `eslint`/`vitest` to patched versions. Remaining `npm audit` items (postcss/sharp) only resolve via a breaking Next 16 upgrade — deferred.
- **CORS fix (merged into main):** Added `CORSMiddleware` to the FastAPI app. Allowed origins come from the `FRONTEND_URL` env var (comma-separated, defaults to `http://localhost:3000`). Methods: GET/POST/OPTIONS; headers: Content-Type; credentials allowed. This resolved the "Network error — could not reach the backend" issue in the upload portal.
- **v0.3.0 scoring agent:** Single Groq-powered agent with hardcoded 4-criteria rubric (problem_fit, technical_depth, feasibility, innovation), JSON response format enforcement, retry/backoff for rate limits (429) and malformed JSON recovery. `POST /api/submissions/{id}/score` endpoint fetches parsed text, scores, and stores results in `scores` table. `GROQ_API_KEY` added to `.env.example` and `backend/config.py`. Committed on `feature/v0.3.0-scoring-agent` (commit `51e7fef`).
- **Default Groq model switched to `openai/gpt-oss-120b`:** `llama-3.3-70b-versatile` was removed from Groq's free tier (404 model_not_found at runtime). `openai/gpt-oss-120b` is the roadmap's listed alternative and is available on the account. Verified end-to-end (commit `869aaf7`).
- **Unicode dash normalization:** PDF/PPTX generators emit typographic dash variants (U+2010-U+2014, U+2212) that extractors pass through verbatim and the LLM echoes into justifications. Added `normalize_unicode_dashes()` in the parsing agent (applied to all extracted text) and to LLM justifications in the scoring agent (commit `d5172bf`).

## Blockers / open questions
- Submissions parsed before the dash-normalization fix keep their Unicode dashes in `parsed_submissions` — acceptable; new uploads are clean. Re-parsing old rows is not planned.
- Remaining frontend `npm audit` vulnerabilities (postcss, sharp) require a breaking Next 16 upgrade — decide whether to do this later.

## Next step
- Start v0.4.0 checkpoint: confirm the full core loop (upload → parse → score) is demoable end to end — all migrations are run, `GROQ_API_KEY` is in `.env`, and the scoring path is already verified against a real submission. Recommend a fresh session for v0.4.0 per session-efficiency rules.
