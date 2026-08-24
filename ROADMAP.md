# ROADMAP.md

- Refer to `docs/hackathon_evaluator_roadmap.md` for the complete roadmap with all the details.

## Now

- Review/merge `feature/v0.3.6-gemini-vision-provider` (optional Gemini image-describer; live check optional with a real `GEMINI_API_KEY`).
- Verify v0.3.5 after Groq TPD reset: re-upload scango.pdf, confirm diagrams land in image_cache, then tag v0.3.5.

## Done

- v0.3.6 — Optional Gemini vision provider for image descriptions: VISION_PROVIDER switch, Groq/qwen default unchanged, scoring untouched; REST-over-httpx (no new dependency). Committed on feature branch — merge pending review. (2026-08-24)
- v0.3.5 — Visual content understanding (diagrams, flowcharts, architecture images): merged to main; tag pending post-reset verification. (2026-08-23)
- v0.3.0 — Single scoring agent: Groq-powered, hardcoded rubric, structured JSON score output. (2026-08-22)
- v0.2.0 — Parsing agent: extract structured text from both PDF (PyMuPDF) and PPTX (python-pptx). (2026-08-21)
- v0.1.0 — Project skeleton: upload portal, Supabase DB + storage wired, submissions stored on upload. (2026-08-20)

## Next

- v0.4.0 — Checkpoint: core loop (upload → parse → score) demoable end to end before adding multi-agent complexity.
- v0.5.0 — Multi-agent split: four specialist agents (problem fit, technical depth, feasibility, innovation) running in parallel, technical depth inferred from document content only (no GitHub dependency).
- v0.6.0 — Weighted scoring + ranking: configurable rubric, composite score, ranked leaderboard, shortlist cutoff.
- v0.7.0 — Feedback agent + export: written per-team rationale, CSV export, per-team PDF export.
- v1.0.0 — Milestone: usable, demo-ready MVP, fully free-tier.

## Later / Ideas

- v1.x — Team-facing polish: submission UX improvements, status tracking, email notifications, appeal flow.
- v2.x — Trust & safety layer: evaluator dashboard with override, audit trail, explainability (cited excerpts), local plagiarism/similarity detection, bias/anomaly flagging.
- v2.5.0 (optional) — GitHub repo analysis as a bonus signal only, never a requirement.
- v3.x — Scale features: multi-track rubric support, analytics dashboard, live pitch transcription, team-facing Q&A chatbot, external integrations, mobile evaluator app.

## Explicitly Not Planned

- Any paid API or service — the project must remain entirely free-tier.
- Making GitHub repo analysis a required input — PDF/PPTX must always be sufficient on their own.
- Building the mobile app, live pitch evaluation, or multi-track support as part of the initial build phases (Now/Next) — these are deferred to Later/Ideas at the earliest.
