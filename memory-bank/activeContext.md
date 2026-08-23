# Active Context

<!-- Update this at the end of every session. This is the first thing to read when resuming. -->

## Current focus
v0.3.5 (visual content understanding) is **merged to `main` and pushed — NOT yet tagged**. Live E2E verification was completed against two real files: Clarix.pptx fully green (descriptions, structural filter, review flags, ~14x cache speedup on duplicate upload, diagram-informed scoring); scango.pdf exposed Groq qwen3.6 free-tier **200k tokens-per-DAY cap** — post-exhaustion vision calls 429 and images degrade by design to `description: null` + `needs_human_review: true` (uncached, auto-retried on later uploads). Two fixes shipped from live testing: PGRST116 500 on missing parsed rows -> clean 404 (`b6e4097`), and a rate-limit circuit breaker so one exhausted quota doesn't burn doomed calls per remaining image (`89daf5b`). 105 tests pass; ruff clean.

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
- **v0.3.5 vision provider is `qwen/qwen3.6-27b`:** live spike (`scripts/check_groq_vision.py`) showed llama-4-scout 404s on this free account and groq/compound rejects multimodal content parts; qwen3.6 accepted base64 PNG input and read text in the image correctly. Its responses include reasoning blocks that `describe.py` strips before storing. Gemini fallback deliberately NOT built speculatively (ADR-0002).
- **Image pipeline is DB-free via dependency injection:** `process_submission_images()` takes `cache_get`/`cache_put` callables so agents never import Supabase; the backend injects the service functions. Cache lookup = exact phash match then near-match scan (hamming <= PHASH_HAMMING_THRESHOLD=8), centralized in `backend/services/supabase.py`.
- **Graceful degradation rule for image understanding:** per-image failures never abort a run — classification failure skips the image; description failure stores `description: null` + `needs_human_review: true` and is NOT cached (retryable); whole-pipeline failure at the route logs a warning and stores empty descriptions. Valid uploads can never be blocked by image stages.
- **pHash fixture lesson:** flat-color/simple images alias together in pHash space (left-half vs top-half differ by only ~4 bits); test fixtures must use structurally distinct shapes (verified empirically via `scripts/check_phash_distances.py`).

## Blockers / open questions
- Submissions parsed before the dash-normalization fix keep their Unicode dashes in `parsed_submissions` — acceptable; new uploads are clean. Re-parsing old rows is not planned.
- Remaining frontend `npm audit` vulnerabilities (postcss, sharp) require a breaking Next 16 upgrade — decide whether to do this later.
- Migrations 0004/0005 ARE applied (user, 2026-08-23). Live test data remains in Supabase: submissions `Clarix` (6e547440...), `Clarix-Duplicate` (0631f0a9...), `v0.3.5 Test 3`/scango.pdf (7a4f19ec...), plus image_cache/scores rows — kept for inspection; safe to delete later.
- Known limitation (by design): some images (e.g. Clarix slide-4 arrows graphic phash d44a2bb53ea236a5; all uncached scango diagrams while TPD was exhausted) store as `description: null` + `needs_human_review: true`. They are NOT cached, so future uploads retry them automatically.
- User accidentally deleted some table entries earlier (orphaned submission dd5f3f5a...); harmless after the PGRST116 fix.

## Next step
- After the Groq TPD window resets: re-upload `scango.pdf`, confirm the page 5/6/7 diagrams land in `image_cache`, then tag `v0.3.5` on `main` and push the tag. Afterwards, start v0.4.0 checkpoint in a fresh session per session-efficiency rules.
