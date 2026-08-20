# Active Context

<!-- Update this at the end of every session. This is the first thing to read when resuming. -->

## Current focus
v0.1.0 (project skeleton) is implemented and tested. Next up is v0.2.0 (parsing agent).

## Recent decisions
- Chose FastAPI + Supabase (Postgres + Storage) for v0.1.0, matching the established tech-stack. No local SQLite fallback — real Supabase keys will be added.
- Backend upload endpoint: `POST /api/submissions` validates file type (.pdf/.pptx) and size (50 MB), uploads to Supabase Storage, inserts a `submissions` row.
- Frontend: minimal Next.js upload portal with client-side file-type validation.
- Pinned `pydantic==2.12.4` (not 2.10.4) because 2.10.4's `pydantic-core` has no Python 3.14 wheel and fails to build on this machine.
- Pinned `httpx==0.27.2` (not 0.28.1) to satisfy `supabase==2.9.0`'s `httpx<0.28` constraint.
- Upgraded `next` to `15.5.23` (patched CVE-2025-66478) and `eslint`/`vitest` to patched versions. Remaining `npm audit` items (postcss/sharp) only resolve via a breaking Next 16 upgrade — deferred.

## Blockers / open questions
- Supabase credentials not yet in `.env` — user needs to create a project, run the SQL migration, create the `submissions` storage bucket, and fill in `.env` (see `docs/setup.md`).
- Remaining frontend `npm audit` vulnerabilities (postcss, sharp) require a breaking Next 16 upgrade — decide whether to do this later.

## Next step
- User: set up Supabase per `docs/setup.md` and fill in `.env`.
- Then: manually verify v0.1.0 end-to-end (upload a PDF and PPTX, confirm storage + DB row, confirm `.exe`/`.docx` rejected).
- Then: start v0.2.0 (parsing agent).