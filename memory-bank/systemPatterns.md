# System Patterns

<!-- Fill in as patterns emerge, so every session follows the same conventions instead of inventing new ones. -->

## Naming conventions

- **Python (backend + agents):** `snake_case` for variables, functions, and modules; `PascalCase` for classes and dataclasses; `UPPER_SNAKE_CASE` for module-level constants.
- **TypeScript/React (frontend):** `camelCase` for variables and functions; `PascalCase` for components and types; `UPPER_SNAKE_CASE` for constants.
- **SQL migrations:** `NNNN_description.sql` — zero-padded sequential numbering (e.g. `0001_create_submissions.sql`).
- **Git branches:** `feature/v0.x.0-short-name` or `fix/short-name` (per `.clinerules/05-git-workflow.md`).

## Folder structure logic

- `/backend` — FastAPI application: `main.py` (entry point + middleware), `config.py` (env-based settings), `routes/` (APIRouter modules), `services/` (external-service wrappers), `tests/`.
- `/agents` — Independent Python LLM/processing modules. Each agent is a narrow, self-contained module (e.g. `agents/parsing/extractor.py`). Tests live in `agents/tests/`.
- `/frontend` — Next.js (TypeScript) app with `app/` directory structure.
- `/infra/migrations` — SQL migration files, applied in filename order.
- `/memory-bank` — Session context: `progress.md`, `activeContext.md`, `systemPatterns.md`, `architecture.md`, `projectBrief.md`, `tech-stack.md`.
- `/docs` — Long-form docs: roadmap, ADRs, setup guides.
- `/.clinerules` — Project-wide rules (security, commit style, testing, git workflow, etc.).

## Common patterns used in this project

- **Supabase access is centralized.** All Supabase interactions go through `backend/services/supabase.py`, which exposes a narrow API (`get_client`, `upload_submission_file`, `insert_submission`, `insert_parsed_submission`). The rest of the backend never imports `supabase` directly.
- **Configuration via environment variables.** `backend/config.py` loads `.env` from the repo root via `python-dotenv` and exposes a `Settings` singleton. No credentials are ever hardcoded.
- **Parse-before-persist.** In `POST /api/submissions`, the file is parsed into structured text *before* any Supabase upload/insert. This ensures corrupt or unparseable files are rejected cleanly (HTTP 422) without leaving orphaned storage objects or DB rows.
- **File validation in the route handler.** File type is validated by extension (never trusting the client's MIME type), file size is checked against `MAX_UPLOAD_BYTES` (50 MB), and team name is validated for non-emptiness — all before reading the full file body where possible.
- **Agents are independent modules.** The parsing agent (`agents/parsing/extractor.py`) is imported by the backend but is a standalone module with its own tests. Future scoring agents will follow the same pattern: narrow, self-contained, independently testable.
- **Tests mock external services.** Backend tests use `monkeypatch` to replace the Supabase service layer, so tests never hit the network. Test fixtures build real in-memory PDF/PPTX files using `fitz` (PyMuPDF) and `python-pptx` for integration-style coverage.
- **CORS is configured in `main.py`.** Allowed origins come from the `FRONTEND_URL` env var (comma-separated, defaults to `http://localhost:3000`).
- **Dataclasses for structured return types.** The parsing agent returns a `ParsedDocument` dataclass (`source_format`, `raw_text`, `sections`) rather than a raw dict, giving type safety and clear documentation.
- **Custom exception hierarchy.** `ParsingError` and `UnsupportedFormatError` in the parsing agent; `SupabaseNotConfiguredError` in the service layer — each maps to a specific HTTP status code in the route handler.
- **Extracted text is normalized to ASCII-safe characters.** `normalize_unicode_dashes()` in the parsing agent converts typographic dash variants (U+2010–U+2014, U+2212) to plain hyphens at extraction time; the scoring agent applies the same function to LLM justifications. Never store or prompt with raw typographic dashes — they break Windows consoles and downstream consumers.
- **Groq retry policy.** Only `RateLimitError` (429) and `APIConnectionError` are retried, with exponential backoff (1s doubling, max 3 retries). Malformed/invalid JSON responses get a corrective re-prompt retry loop per agent in `SpecialistAgent.score`. All other Groq errors propagate immediately.
- **Ranking composites are computed on the fly (v0.6.0), never persisted** — the leaderboard always reflects current rubric weights and freshly scored submissions with zero denormalization drift. Ranking logic is PURE and lives in `agents/ranking/engine.py`; backend routes/services fetch rows and delegate. Tie order is a deterministic chain: composite DESC → innovation DESC → submission_id ASC; composites are rounded to 4dp BEFORE tie grouping so tied values are bit-identical floats. Cutoffs (`top_n` | `min_score`, inclusive) are mutually exclusive — the route 422s when both are given. Only complete four-criterion score sets rank; unscored/partial submissions are excluded but reported via counts.
- **Rubric fallback is visible, not silent.** A missing or partially-configured `rubric_config` for a hackathon falls back to equal weights AND the rankings response says `"rubric_source": "fallback"` so operators never mistake defaults for deliberate config.
- **Scoring is a parallel fan-out of four specialists (v0.5.0).** Each criterion has its own tiny module in `agents/scoring/` subclassing `SpecialistAgent`; `base.py` owns the shared plumbing — prompt scaffolding, the `_get_async_groq_client` seam, backoff through an `_sleep` indirection (tests patch that instead of mutating global asyncio), and single-criterion JSON validation. `scorer.score_submission` gathers all four against ONE shared AsyncGroq client with `return_exceptions=True` and raises the first failure — **fail-closed**: never store partial score rows. Results are re-ordered canonically by `CRITERIA_NAMES` regardless of completion order. No artificial staggering: 4 concurrent calls sit far below Groq's ~30 RPM. Keep each agent module to criterion + guidance lines only; don't collapse them back into one prompt.
- **Booleans pass int checks in Python.** When validating LLM JSON scores, reject `isinstance(x, bool)` explicitly before `int()` coercion/range checks — otherwise `True` counts as score 1.
- **Scorer test fakes must be async.** Anything monkeypatched over `backend.routes.scoring.score_submission` is `async def fake_score(...)` as of v0.5.0 (the route awaits the orchestrator).
- **Default Groq model is `openai/gpt-oss-120b`.** `llama-3.3-70b-versatile` was removed from Groq's free tier (404 model_not_found) — do not reference it in new code.
- **Image understanding is a DB-free pipeline with injected dependencies.** `agents/parsing/images/pipeline.py` takes `cache_get`/`cache_put` (and optionally `classify_fn`/`describe_fn`) callables — agents never import Supabase; the backend injects service functions. Cache lookup = exact phash match, then near-match scan within `PHASH_HAMMING_THRESHOLD`, centralized in the Supabase service layer.
- **Image-stage failures degrade gracefully; they never block uploads.** Classification failure -> skip that image; description failure -> store `description: null` + `needs_human_review: true` and don't cache (retryable); whole-pipeline failure at the route -> log warning, store empty descriptions.
- **Cache-first image classification.** Check `image_cache` by perceptual hash BEFORE calling CLIP or the vision LLM; only successful descriptions are cached (failures stay retryable); high-confidence decorative images are dropped and never cached.
- **Groq vision model is `qwen/qwen3.6-27b`** (`GROQ_VISION_MODEL`). llama-4-scout 404s on free accounts; groq/compound rejects multimodal content parts. qwen responses include reasoning blocks — always strip them before storing/using the text (see `describe.py::_strip_think_blocks`).
- **pHash test fixtures must be structurally distinct shapes.** Flat colors and simple half-plane fills alias together in pHash space (distances as low as 4 between "different" images). Verify fixture separation empirically with `scripts/check_phash_distances.py`.
- **Never use PostgREST `.single()` for optional lookups.** It RAISES `APIError PGRST116` on zero rows instead of returning empty data (caused an unhandled 500 when scoring a missing submission id). Use `.limit(1)` + explicit `None` return — see `get_parsed_submission`.
- **Groq free tier has per-model tokens-per-DAY caps** (qwen3.6-27b: 200k TPD) on top of RPM limits — vision calls burn thousands of tokens each, so heavy testing exhausts the day budget fast. When exhausted, every call 429s until the window resets; failed descriptions degrade to `null` + review flag and auto-retry on later uploads.
- **Rate-limit circuit breaker inside a pipeline run:** once describe() exhausts its retries on a 429, remaining images skip the vision call entirely (flagged, uncached) instead of burning doomed calls — quota is respected and failures stay retryable across submissions.
- **Vision provider is pluggable via `VISION_PROVIDER` (`groq` default | `gemini`).** The resolver lives in `pipeline._resolve_default_describer()`; scoring/text stages are always Groq regardless. The Gemini describer (`describe_gemini.py`) calls Google's REST endpoint through pinned httpx — the `google-genai` SDK is BANNED here because it needs `httpx>=0.28` vs supabase's `httpx<0.28`. Default `GEMINI_VISION_MODEL=gemini-3.6-flash`; Google retires models per-key-cohort (2.5-flash 404s "no longer available to new users" on fresh keys even while still catalog-listed) — non-retryable HTTP errors log Google's JSON error body before propagating.
- **`VisionRateLimitError` subclasses `groq.RateLimitError`** so the pipeline's single `except RateLimitError` breaker trips for ANY vision provider; non-Groq describers raise it after exhausting retries (it builds a synthetic `httpx.Response(429)` internally — groq's APIStatusError reads `response.request`, so None crashes).
- **Decorative-labeled CLIP results are never vision-described (any confidence); ambiguous decorative tops get a diagram-floor rescue inside classify.py** — if the best diagram-label probability ≥ `IMAGE_DIAGRAM_FLOOR` (default 0.30, calibrated on scango.pdf: banners ≤0.27, misread flow 0.32), that diagram label replaces the top so routing describes it. The rescue lives in classify.py because it owns the probs — keeps the pipeline's 2-tuple ClassifyFn contract intact.
- **Always pass `force_quick_gelu=True` when loading OpenAI-pretrained CLIP weights** — without it open_clip warns and embeddings silently degrade.
- **CHANGELOG regeneration runs `scripts/regenerate_changelog.py <last-covered-sha>..HEAD`** (wraps git-cliff; docs/chore commits filtered; generated bullets merge into the top of matching `[Unreleased]` sections with sha links).

- **Project version lives in root `version.py` (`APP_VERSION`).** Bump it together with the git tag and `frontend/package.json` in the same commit; FastAPI/OpenAPI metadata, the scorer's `AGENT_VERSION` (persisted per score row as provenance), and the README status line all derive from it. Per-module provenance strings (e.g. `DESCRIBER_VERSION`) intentionally track their own last-change release instead. Drift guard: `backend/tests/test_version.py`.

## Things to avoid

- **No hardcoded secrets.** Everything goes in `.env` (loaded via `python-dotenv`). `.env` and `.env.local` are in `.gitignore`.
- **No paid services.** Only free-tier APIs and open-source libraries (Groq, Supabase free tier, PyMuPDF, python-pptx, etc.).
- **No GitHub dependency.** PDF/PPTX must always be sufficient. GitHub repo analysis is optional (v2.5.0, stretch).
- **Don't collapse scoring agents.** Keep the four specialist agents as independent, narrowly-scoped modules — don't merge them into a single prompt.
- **No `git add .` blindly.** Stage only relevant files per `.clinerules/02-commit-style.md`.
- **No committing directly to `main`.** Use feature branches per `.clinerules/05-git-workflow.md`.