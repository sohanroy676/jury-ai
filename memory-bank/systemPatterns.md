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
- **Groq retry policy.** Only `RateLimitError` (429) and `APIConnectionError` are retried, with exponential backoff (1s doubling, max 3 retries). Malformed/invalid JSON responses get a corrective re-prompt retry loop in `score_submission`. All other Groq errors propagate immediately.
- **Default Groq model is `openai/gpt-oss-120b`.** `llama-3.3-70b-versatile` was removed from Groq's free tier (404 model_not_found) — do not reference it in new code.
- **Image understanding is a DB-free pipeline with injected dependencies.** `agents/parsing/images/pipeline.py` takes `cache_get`/`cache_put` (and optionally `classify_fn`/`describe_fn`) callables — agents never import Supabase; the backend injects service functions. Cache lookup = exact phash match, then near-match scan within `PHASH_HAMMING_THRESHOLD`, centralized in the Supabase service layer.
- **Image-stage failures degrade gracefully; they never block uploads.** Classification failure -> skip that image; description failure -> store `description: null` + `needs_human_review: true` and don't cache (retryable); whole-pipeline failure at the route -> log warning, store empty descriptions.
- **Cache-first image classification.** Check `image_cache` by perceptual hash BEFORE calling CLIP or the vision LLM; only successful descriptions are cached (failures stay retryable); high-confidence decorative images are dropped and never cached.
- **Groq vision model is `qwen/qwen3.6-27b`** (`GROQ_VISION_MODEL`). llama-4-scout 404s on free accounts; groq/compound rejects multimodal content parts. qwen responses include reasoning blocks — always strip them before storing/using the text (see `describe.py::_strip_think_blocks`).
- **pHash test fixtures must be structurally distinct shapes.** Flat colors and simple half-plane fills alias together in pHash space (distances as low as 4 between "different" images). Verify fixture separation empirically with `scripts/check_phash_distances.py`.

## Things to avoid

- **No hardcoded secrets.** Everything goes in `.env` (loaded via `python-dotenv`). `.env` and `.env.local` are in `.gitignore`.
- **No paid services.** Only free-tier APIs and open-source libraries (Groq, Supabase free tier, PyMuPDF, python-pptx, etc.).
- **No GitHub dependency.** PDF/PPTX must always be sufficient. GitHub repo analysis is optional (v2.5.0, stretch).
- **Don't collapse scoring agents.** Keep the four specialist agents as independent, narrowly-scoped modules — don't merge them into a single prompt.
- **No `git add .` blindly.** Stage only relevant files per `.clinerules/02-commit-style.md`.
- **No committing directly to `main`.** Use feature branches per `.clinerules/05-git-workflow.md`.