# Active Context

<!-- Update this at the end of every session. This is the first thing to read when resuming. -->

## Current focus

**v3.2.0 + v3.1.0 SHIPPED & MERGED TO MAIN (2026-09-01).** 
- Multi-track scoping (`/api/tracks`, `/api/rubrics/{trackId}`, `/api/rankings?hackathon_id=...`, track selector dropdowns on submission portal & evaluator dashboard).
- Analytics dashboard (`/dashboard/analytics`: score distributions, criterion heatmap, submission funnel).
- Modern dark glassmorphism design system (`Outfit`, `Inter`, `JetBrains_Mono`), HSL/gradient progress bar fills, session-persistent track selection (`sessionStorage`), zero full-page form reloads (`e.preventDefault()`), quiet background polling in submission detail view (`fetchData`).
- All tests passing: 432 / 432 Pytest backend tests, 52 / 52 Vitest frontend tests, zero ESLint/Ruff errors.

**Single next step for the next session:** Confirm `main` state and proceed with **v2.6.0 Bias & Anomaly Flagging** (migration 0013 `confidence` column, `agents/analysis/flags.py` pure module, flag display in leaderboard + detail view).

## Recent decisions

- **Track Selection Persistence**: Selected evaluation tracks are stored in `sessionStorage` (`juryai_active_track`) so track context stays sticky across pages, batch operations, and browser reloads.
- **Form Submit Isolation**: All form submit handlers (`handleBatchScore`, `handleBatchFeedback`, etc.) explicitly call `e.preventDefault()` to prevent standard HTTP form submit reloads in Next.js.
- **Progress Bar Fills**: Progress bar tracks and fills use `display: block` with `!important` gradient colors to ensure progress bars render cleanly across all browser engines.
- **Quiet Polling**: Background polling in `SubmissionDetailView.tsx` uses `fetchData(false)` to update data silently without setting `loading = true` or unmounting component UI.
- **Email problems never raise — they return.** `services/email.py` dispatch validates recipient/provider/config and returns `EmailResult(status∈sent|skipped|failed, reason, detail)`.
- **Export links forward live cutoff.** `exportCsvUrl`/`exportPdfUrl` forward `top_n`/`min_score` so exports match the evaluator's active screen view.

## Blockers / open questions

- **None** — v3.2.0 & v3.1.0 live-verified and committed; test suites green.
