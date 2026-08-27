# Active Context

<!-- Update this at the end of every session. This is the first thing to read when resuming. -->

## Current focus

**v1.2.0 LIVE-VERIFIED & RELEASING (2026-08-26).** User confirmed: migrations applied, SMTP configured, real emails received — including the fixed explicit reject/shortlist wording. Full suites green on the release tree (pytest **392**, Vitest **45**). Branch stack `feature/v1.2.0-notifications` ← `feature/v1.2.0-batch-feedback` ← `fix/results-email-explicit-outcome` fast-forwards to `main`; tag `v1.2.0`; push approved by user this session. Delivered in v1.2.0: team_email collection (migration 0009 + portal field), confirmation + results emails over `EMAIL_PROVIDER=smtp|resend` (`services/email.py`, ADR-0004), one-click batch feedback (`POST /api/submissions/feedback-pending` + dashboard control), explicit shortlist/reject outcome copy in emails. Deadline reminder DEFERRED (needs roster/deadline model — see ROADMAP Next).

**Current focus: v1.3.0 Appeal flow — IMPLEMENTED on `feature/v1.3.0-appeals`.** Backend complete (188 tests pass, ruff clean). Frontend complete (code follows conventions; vitest/eslint could not be run — Node.js not installed in this env). Ready for user review/merge. Next: commit per conventional-commits style, regenerate CHANGELOG via /commit workflow, update ROADMAP.md to move v1.3.0 from Now to Done.

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

