# Active Context

<!-- Update this at the end of every session. This is the first thing to read when resuming. -->

## Current focus

**v1.1.0 SHIPPED & PUSHED (2026-08-25).** Tag `v1.1.0` (annotated) on `a319e80`; `main` and `v1.1.0` tag both pushed to origin — `main...origin/main` clean, working tree clean. The CSV/PDF shortlist-cutoff bug (Export CSV downloading a board where every team shows "no" despite a top-3 shortlist shown on screen) is fixed and regression-covered; migration `0008_allow_resubmission.sql` was applied by the user and live-verified. **Next: v1.2.0 Email notifications** (confirmation on upload, reminder before deadline, results-with-feedback via Gmail SMTP or Resend free tier) — start in a new session that reads this memory-bank first (06-session-efficiency).

## Recent decisions

- **Export links must forward the shortlist cutoff that produced the view.** The engine treats "no cutoff" as nobody-shortlisted, so an Export CSV / PDF link built without `top_n`/`min_score` silently exports a different board than what the evaluator sees. Both `exportCsvUrl`/`exportPdfUrl` now take cutoff params and every call site forwards live state (`appliedTopN` on the dashboard, the top-N input on the detail view).
- **v1.1.0 pipeline stages are DERIVED, never stored.** The StageTracker computes Submitted/Parsed/Scored from real artifacts (row exists / parsed row present / complete four-criterion set) and the final Shortlisted-vs-Rejected label from the FeedbackAgent verdict — `submissions.status` stays untouched, mirroring the compute-on-the-fly convention used for ranking composites.
- **Portal forms drop native `required`; inline validation owns the messaging.** Submit is additionally gated by `formReady`. Testing lesson (root-caused with a DIAG probe): jsdom's constraint validation silently swallows submit clicks when a `required` file input receives programmatic files — `files.length` is 1 but `value` stays empty, so the form reports valueMissing.
- **Re-submission identity = case-insensitive exact team_name, and archive-before-insert ordering is load-bearing.** `get_active_submission_by_team` narrows with ilike but re-verifies equality in Python because PostgREST ilike treats `%`/`_` as wildcards; `insert_submission(supersedes_team=True)` stamps prior actives before inserting the new row so a crash can never leave two active rows.
- **Migration 0008 is a hard RUNTIME dependency, not a formality:** submission routes filter `superseded_at`, so pointing the backend at an un-migrated database fails every upload/list/ranking call until it is applied.
- **v1.0.0 release smoke used TestClient instead of a socket server.** Booting uvicorn adds port/lifecycle management for zero benefit in read-only probing; instantiating the ASGI app directly loads `.env` and talks to real Supabase in-process. All read paths returned 200 against production data (feedback row present → migration 0007 confirmed) without spending any Groq quota.
- **Prettier churn policy verified before staging:** `npm run format` touched 22 files but only 8 had content diffs (wrapping/EOF fixes); the rest were CRLF↔LF working-copy noise absorbed by `core.autocrlf` at commit time — checked via `git diff --stat` so no formatter churn entered history.
- **CORS PUT preflight fix** — the dashboard rubric save was unreachable from the browser (UI "Network error"; terminal `OPTIONS /api/rubrics/default 400`). Root cause: `CORSMiddleware` allowed only GET/POST/OPTIONS; `PUT /api/rubrics` (v0.6.0, the API's only PUT route) forces a preflight Starlette answered 400 "Disallowed CORS method". Fixed by adding `"PUT"` to `allow_methods`; `test_cors_preflight_allows_put_for_rubrics` guards it (400 before, 200 after). Lesson: any NEW HTTP verb on any route needs a matching CORS preflight test.

## Blockers / open questions

- **None for v1.1.0** — shipped and pushed; no blocking items for the next session.
- **v1.2.0 starter tasks** (carry forward): (1) read `docs/hackathon_evaluator_roadmap.md` §v1.2.0 for the exact email templates + trigger points; (2) decide Gmail SMTP vs Resend free-tier path and add `SMTP_*` / Resend keys to `.env.example` (free-tier only — no paid deps); (3) wire notification triggers into existing `POST /api/submissions` (on parse-complete → send confirmation) and the scoring/feedback completion path (→ send results). Reuse `lib/api.ts` patterns from v1.1.0.
- **Standing hygiene (non-blocking):** the live `default` rubric still holds v0.6.0 test weights (problem_fit 0.15, technical_depth 0.20, feasibility 0.25, innovation 0.40) — reset to equal 25% via the dashboard editor if undesired.
- **Standing hygiene (non-blocking):** live test data left from prior verification cycles exists in Supabase (v0.5.0/v0.6.0 decks, older Clarix/scango rows) — safe to delete later but not blocking.

