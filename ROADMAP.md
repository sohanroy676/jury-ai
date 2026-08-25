# ROADMAP.md

- Refer to `docs/hackathon_evaluator_roadmap.md` for the complete roadmap with all the details.

## Now

- v1.0.0 — Milestone: usable, demo-ready MVP, fully free-tier. *(IMPLEMENTED on `feature/v1.0.0-mvp-dashboard`: evaluator dashboard UI, batch score-pending endpoint, typed frontend API client, backend+frontend test suites — NOT yet verified: full pytest/vitest/lint runs pending (Node missing for frontend side), version bump to 1.0.0 + CHANGELOG regen + merge still to come. See memory-bank/activeContext for exact state.)*

## Done

- v0.7.0 — Feedback agent + export: Groq-powered FeedbackAgent (agents/feedback/agent.py) generates per-team written feedback (strengths, weaknesses, one actionable suggestion, shortlist/reject verdict, tone matching the shortlist decision) from the four criterion scores + justifications; `feedback` table (migration 0007, one current row per submission); `POST|GET /api/submissions/{id}/feedback`; leaderboard CSV export (`GET /api/export/csv`) and per-team ReportLab PDF export (`GET /api/export/submissions/{id}/pdf`) - all reusing the shared `load_leaderboard()` path so exported numbers match GET /api/rankings. Merged fast-forward to main and tagged **v0.7.0** @ 7dbf476. Tests: backend 92 / agents 230, ruff clean. *(Live credential E2E + migration 0007 application still outstanding - see memory-bank/activeContext.)* (2026-08-25)

- v0.6.0 — Weighted scoring + ranking: `rubric_config` table (migration 0006, hackathon-scoped, seeded equal weights); pure ranking engine in `agents/ranking/engine.py` (composite = Σ score×weight computed on the fly, deterministic tie-break composite→innovation→id with tie flags, top-N / min-score shortlists, unscored/partial excluded but counted); `GET /api/rankings` + `GET|PUT /api/rubrics/{hackathon_id}` with fraction-or-percent normalization and fallback-to-equal-weights transparency. LIVE-verified end-to-end (real Supabase+Groq): rubric probe 200 (migration present), innovation-heavy 15/20/25/40 rubric PUT persisted, two live-scored decks landed on the populated board with composites exactly equal to Σ score×weight (Practical 5.1 @ rank 4; Moonshot 4.4 @ rank 6; correct relative order), top_n=2 marked exactly 2 shortlisted, unknown hackathon → `rubric_source: "fallback"` + equal weights. Merged fast-forward to `main` and tagged **v0.6.0**. Tests: backend 58 / agents 195 / frontend 3, ruff clean. (2026-08-24)

- v0.5.0 — Multi-agent split: four independent specialist agents (problem fit, technical depth, feasibility, innovation) score each submission concurrently (`asyncio.gather`, one shared AsyncGroq client, fail-closed aggregation, canonical result ordering); technical depth inferred from document content only (no GitHub dependency); scores schema unchanged (criterion doubles as agent identity beside agent_version v0.5.0). LIVE-verified end-to-end (real Supabase+Groq: score 200 in ~4.8s, four rows at agent_version v0.5.0, sensible cross-agent disagreement — feasibility 9 vs innovation 3 vs technical_depth 4 on the same proposal). Merged fast-forward to `main` and tagged **v0.5.0**. Tests: backend 38 / agents 166 / frontend 3, ruff clean. (2026-08-24)
- v0.4.0 — Checkpoint passed: core loop (upload → parse → score) demoable end to end. Added read API (GET /api/submissions list + detail composing submission/parsed/scores), mocked-loop integration test, curl demo docs; LIVE-verified end-to-end (real Supabase + Groq, agent_version v0.4.0 persisted per score row). Also: project version centralized in root version.py (FastAPI metadata, scorer provenance, package.json, README all derive; drift-guard tests), CHANGELOG rebuilt as newest-first per-version sections via rewritten regenerate_changelog.py (+ local tags v0.1.0/v0.2.0). Tests: backend 38 / agents 106 / frontend 3, ruff clean. (2026-08-24)
- v0.3.6 — Optional Gemini vision provider for image descriptions + model-404 fix + classification-routing fix: VISION_PROVIDER switch, gemini-3.6-flash default (REST over pinned httpx), decorative images never described, diagram-floor rescue relabels misread diagrams. Merged to `main` and tagged **v0.3.6**. (2026-08-24)
- v0.3.5 — Visual content understanding (diagrams, flowcharts, architecture images): merged to main; verified live (scango.pdf end-to-end, image_cache populated) and tagged **v0.3.5**. (2026-08-23)
- v0.3.0 — Single scoring agent: Groq-powered, hardcoded rubric, structured JSON score output. (2026-08-22)
- v0.2.0 — Parsing agent: extract structured text from both PDF (PyMuPDF) and PPTX (python-pptx). (2026-08-21)
- v0.1.0 — Project skeleton: upload portal, Supabase DB + storage wired, submissions stored on upload. (2026-08-20)

## Next

- v1.x — Team-facing polish: submission UX improvements, status tracking, email notifications, appeal flow.

## Later / Ideas

- v2.x — Trust & safety layer: evaluator dashboard with override, audit trail, explainability (cited excerpts), local plagiarism/similarity detection, bias/anomaly flagging.
- v2.5.0 (optional) — GitHub repo analysis as a bonus signal only, never a requirement.
- v3.x — Scale features: multi-track rubric support, analytics dashboard, live pitch transcription, team-facing Q&A chatbot, external integrations, mobile evaluator app.

## Explicitly Not Planned

- Any paid API or service — the project must remain entirely free-tier.
- Making GitHub repo analysis a required input — PDF/PPTX must always be sufficient on their own.
- Building the mobile app, live pitch evaluation, or multi-track support as part of the initial build phases (Now/Next) — these are deferred to Later/Ideas at the earliest.
