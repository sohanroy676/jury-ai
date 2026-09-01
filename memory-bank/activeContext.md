# Active Context

<!-- Update this at the end of every session. This is the first thing to read when resuming. -->

## Current focus

**v2.3.0 + v2.1.0 BOTH MERGED TO MAIN (2026-09-01).** Explainability (cited excerpts on every score) and evaluator overrides (override endpoint + modal + flagged-image review queue + dashboard redesign) are complete, tested, and fast-forward merged. Latest commit on `main`: `5fe0ce0`. NOT yet pushed — awaiting user approval. Migrations 0010 + 0011 need manual application in Supabase SQL Editor (see docs/setup.md). Full suites green: pytest 405 (needs `--ignore=agents/tests/test_image_classify.py` for the torch gap in this venv), vitest 52, ruff clean, next lint clean.

**Single next step for the next session:** fresh session per `feature/v2.1.0-evaluator-override`→`main` state, then begin **v2.2.0 Audit trail** (migration 0012 `audit_log` table, `backend/services/audit.py`, timeline UI in SubmissionDetailView) — v2.1.0's override provenance columns were designed to feed it. Remaining in the approved batch after that: v1.3.0 appeal flow, v3.1.0 anomaly flagging, v3.2.0 analytics dashboard, then roadmap reorder + changelog + version bump to 2.1.0 for release.

**Single next step for the next session:** open a fresh session (it reads this memory-bank first), confirm `main`/`v1.2.0` tag state, and begin **v1.3.0 Appeal flow** per `docs/hackathon_evaluator_roadmap.md` §v1.3.0.

## Recent decisions

## Recent decisions

- **Email problems never raise — they return.** `services/email.py` dispatch validates recipient/provider/config and returns `EmailResult(status∈sent|skipped|failed, reason, detail)`; a broad except maps transport errors to failed+logged. Rationale: an unconfigured/broken mail transport must not break uploads or feedback (image-stage degradation philosophy). Responses expose only `{status, reason}` — detail stays in logs.
- **Dual transport behind `EMAIL_PROVIDER` (smtp default | resend)** per explicit user decision. Resend implemented as hand-rolled REST over pinned httpx because its SDK needs httpx>=0.28 vs supabase's `<0.28` pin (same trap as google-genai in ADR-0003); retry policy mirrors Gemini describer: ONLY 429/transport ×3 exponential backoff via `_sleep`.
- **team_email semantics**: nullable column, blank input stored NULL (DB CHECK allows null not ''); API treats it optional while the portal REQUIRES a valid address (formReady gate) — Postel leniency at the boundary, strictness in UX.
- **Feedback regeneration deliberately re-emails**: every successful generation produces the team's current official result, so re-notifying is correct; failures never reach the mail line.
- **Route tests touching POST /submissions or feedback MUST autouse-mock the mailer** — the developer's real `.env` may hold live SMTP credentials; this keeps `pytest` permanently incapable of sending real mail.
- **main.py CORS origins now come from Settings.frontend_urls** (single getenv parse; first entry doubles as the email link base URL).

- **Export links must forward the shortlist cutoff that produced the view.** The engine treats "no cutoff" as nobody-shortlisted, so an Export CSV / PDF link built without `top_n`/`min_score` silently exports a different board than what the evaluator sees. Both `exportCsvUrl`/`exportPdfUrl` now take cutoff params and every call site forwards live state (`appliedTopN` on the dashboard, the top-N input on the detail view).
- **v1.1.0 pipeline stages are DERIVED, never stored.** The StageTracker computes Submitted/Parsed/Scored from real artifacts (row exists / parsed row present / complete four-criterion set) and the final Shortlisted-vs-Rejected label from the FeedbackAgent verdict — `submissions.status` stays untouched, mirroring the compute-on-the-fly convention used for ranking composites.
- **Portal forms drop native `required`; inline validation owns the messaging.** Submit is additionally gated by `formReady`. Testing lesson (root-caused with a DIAG probe): jsdom's constraint validation silently swallows submit clicks when a `required` file input receives programmatic files — `files.length` is 1 but `value` stays empty, so the form reports valueMissing.
- **Re-submission identity = case-insensitive exact team_name, and archive-before-insert ordering is load-bearing.** `get_active_submission_by_team` narrows with ilike but re-verifies equality in Python because PostgREST ilike treats `%`/`_` as wildcards; `insert_submission(supersedes_team=True)` stamps prior actives before inserting the new row so a crash can never leave two active rows.
- **Migration 0008 is a hard RUNTIME dependency, not a formality:** submission routes filter `superseded_at`, so pointing the backend at an un-migrated database fails every upload/list/ranking call until it is applied.
- **v1.0.0 release smoke used TestClient instead of a socket server.** Booting uvicorn adds port/lifecycle management for zero benefit in read-only probing; instantiating the ASGI app directly loads `.env` and talks to real Supabase in-process. All read paths returned 200 against production data (feedback row present → migration 0007 confirmed) without spending any Groq quota.
- **Prettier churn policy verified before staging:** `npm run format` touched 22 files but only 8 had content diffs (wrapping/EOF fixes); the rest were CRLF↔LF working-copy noise absorbed by `core.autocrlf` at commit time — checked via `git diff --stat` so no formatter churn entered history.
- **CORS PUT preflight fix** — the dashboard rubric save was unreachable from the browser (UI "Network error"; terminal `OPTIONS /api/rubrics/default 400`). Root cause: `CORSMiddleware` allowed only GET/POST/OPTIONS; `PUT /api/rubrics` (v0.6.0, the API's only PUT route) forces a preflight Starlette answered 400 "Disallowed CORS method". Fixed by adding `"PUT"` to `allow_methods`; `test_cors_preflight_allows_put_for_rubrics` guards it (400 before, 200 after). Lesson: any NEW HTTP verb on any route needs a matching CORS preflight test.

## Blockers / open questions

- **None** — v1.2.0 live-verified and released; no blocking items.
- **Standing hygiene (non-blocking):** the live `default` rubric still holds v0.6.0-era weights if never reset via the dashboard editor — reset to equal 25% if undesired.
- **Standing hygiene (non-blocking):** the live `default` rubric still holds v0.6.0 test weights (problem_fit 0.15, technical_depth 0.20, feasibility 0.25, innovation 0.40) — reset to equal 25% via the dashboard editor if undesired.
- **Standing hygiene (non-blocking):** live test data left from prior verification cycles exists in Supabase (v0.5.0/v0.6.0 decks, older Clarix/scango rows) — safe to delete later but not blocking.

