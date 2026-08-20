# projectBrief.md

## What This Is

JuryAI is an agentic AI system that automatically evaluates, ranks, shortlists, and gives written feedback on hackathon submissions (PDFs and PPTX decks). It's built for hackathon organizers and evaluators — any hackathon, with a particular focus on Smart India Hackathon (SIH)-style events — who need to review large volumes of submissions fairly and at scale.

## Core Goal / Success Criteria for v1

v1 is "done" when the full core pipeline works end to end, matching the v1.0.0 milestone from the project roadmap:

- Teams can upload a PDF or PPTX submission through a working portal.
- Submissions are automatically parsed into structured text.
- Four specialist agents (problem fit, technical depth, feasibility, innovation) independently score each submission.
- Scores are combined into a weighted composite score using a configurable rubric.
- Submissions are automatically ranked, with a configurable shortlist cutoff.
- Each team receives AI-generated written feedback (strengths, weaknesses, actionable suggestion).
- Results are exportable as CSV and per-team PDF.
- The entire system runs on free-tier services only — zero ongoing cost.

## Explicitly Out of Scope (for now)

- GitHub repo analysis / code quality checks — technical depth is inferred from the PDF/PPTX content alone; repo checking is a later, optional addition, not a dependency.
- Live pitch / video evaluation and transcription.
- Mobile evaluator app.
- Multi-track rubric support (running multiple hackathon tracks in parallel).
- Analytics dashboards (score distributions, heatmaps).
- Team-facing Q&A chatbot.
- External integrations (e.g. syncing with SIH's actual portal, Slack digests).
- Any paid service or API — the system must run entirely on free tiers.