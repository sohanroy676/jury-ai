# Agentic AI Hackathon Evaluator — Complete Build Roadmap

_Versioned milestones (v0.1.0 → v3.6.0) — 100% free-tier stack_

---

## How to use this roadmap

Each version is a milestone: a working, testable increment. Build it, test it against the checklist, commit, tag the version, then move on. Don't skip the test step — every later version assumes earlier ones actually work, not just compile.

**Git workflow:** one branch per version, merge to `main` and tag (`git tag v0.5.0`) once the test checklist passes.

## Free-tier stack (no money required)

Every paid service from the original plan has a free substitute below. This is the stack used throughout the roadmap.

| Need                                         | Free choice                                                                                                        | Notes                                                                                                                                                          |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LLM inference (all agents)                   | **Groq API** (`llama-3.3-70b-versatile` or `openai/gpt-oss-120b`)                                                  | No credit card. Free tier ≈ 30 requests/min, ~1,000 requests/day, ~6–12K tokens/min per model. No cost, ever — just rate-limited. Sign up at console.groq.com. |
| Backup / second opinion LLM                  | **Google AI Studio (Gemini API free tier)**                                                                        | More generous volume (1,500 req/day, much higher TPM) — good fallback if Groq's RPM is hit during testing.                                                     |
| Embeddings (similarity/plagiarism check)     | **Sentence-Transformers (local, open-source)** via `sentence-transformers` Python package, e.g. `all-MiniLM-L6-v2` | Runs entirely on your machine — zero API cost, no rate limit.                                                                                                  |
| Vector store                                 | **ChromaDB** (local, embedded, free)                                                                               | No hosted Pinecone needed — runs in-process.                                                                                                                   |
| Database                                     | **Supabase free tier** or plain **SQLite/Postgres running locally**                                                | Supabase free tier is generous (500MB DB, 1GB storage) and gives you hosted Postgres + file storage together for zero cost.                                    |
| File storage                                 | **Supabase Storage free tier** (bundled above) or local disk during dev                                            | 1GB free storage is enough for a hackathon-scale pilot.                                                                                                        |
| Email notifications                          | **Gmail SMTP** (free, via `smtplib`) or **Resend free tier** (3,000 emails/month free)                             | Both work without a credit card for low volume.                                                                                                                |
| PDF/PPT text extraction                      | **PyMuPDF** (`fitz`) and **python-pptx** — both open-source, free                                                  | Handles both priority formats natively.                                                                                                                        |
| PDF export (feedback reports)                | **ReportLab** (open-source) or **WeasyPrint**                                                                      | Free, local, no API.                                                                                                                                           |
| Frontend hosting                             | **Vercel free tier** or **Netlify free tier**                                                                      | Fine for a student project's traffic level.                                                                                                                    |
| Backend hosting                              | **Render free tier** or run locally during dev                                                                     | Render's free web service tier sleeps after inactivity — fine for a demo, mention this if you deploy.                                                          |
| Code repo analysis (optional, deprioritized) | **GitHub REST API** (free, no auth needed for public repos at low volume)                                          | Not required for MVP — see priority note below.                                                                                                                |

**Rate-limit awareness:** Groq's free tier caps around 30 requests/minute and roughly 1,000 requests/day per model. For a hackathon-scale pilot (tens to low hundreds of submissions) this is enough, but batch your agent calls with small delays / retries, and consider a queue instead of hammering all 4 agents simultaneously across many submissions at once.

## Priority note: PDF and PPT first, GitHub optional

The original plan treated code-repo analysis as a core input. That's now **deprioritized**:

- **PDF and PPTX are the only required input formats.** Every agent should work fully from parsed document text + slides.
- **GitHub repo checking is optional** — build it only if time remains (see v2.5.0, now marked optional/stretch). If a team doesn't submit a repo link, or you never build that agent, the system should still function completely using just the PDF/PPT content.
- `TechnicalDepthAgent` in v0.5.0 is now scoped to **infer technical depth from the document/slides alone** (architecture descriptions, tech stack mentioned, implementation details written up) rather than requiring live code access.

## Track overview

- **v0.x** — Core pipeline (ingestion → parsing → single agent → multi-agent → scoring → ranking → feedback). Ends at v1.0.0, a usable MVP.
- **v1.x** — Team-facing polish (portal UX, status tracking, notifications, appeals).
- **v2.x** — Trust & safety layer (dashboard, overrides, audit trail, explainability, plagiarism/bias checks).
- **v3.x** — Scale features (multi-track, analytics, live pitch evaluation, integrations, mobile).

---

## v0.x — Core pipeline

### v0.1.0 — Project skeleton

**Goal:** A submission can be uploaded and stored. No intelligence yet — just plumbing.

**Build**

- Set up repo structure: `/frontend` (Next.js), `/backend` (FastAPI or Node/Express), `/agents` (Python, for LLM orchestration), `/infra`.
- Set up Postgres via **Supabase free tier** (or local SQLite for pure offline dev) with a `submissions` table: `id, team_name, file_url, file_type, uploaded_at, status`.
- Set up file storage via **Supabase Storage free tier** for PDFs/PPTs.
- Build a minimal upload form: team name, file picker (accept `.pdf`, `.pptx` only), submit button.
- On submit: upload file to storage, insert a row in `submissions`.

**Test / definition of done**

- Upload a test PDF and a test PPTX through the form.
- Confirm the file appears in storage and a matching row appears in the database.
- Confirm uploading an unsupported file type (e.g. `.exe`, `.docx`) is rejected client-side with a clear message.

---

### v0.2.0 — Parsing agent (PDF + PPTX)

**Goal:** Raw files become structured, queryable text — for both priority formats.

**Build**

- Add a parsing service: given a `file_url`, download the file and extract text.
    - PDFs: **PyMuPDF (`fitz`)** — free, fast, handles text + can rasterize pages if needed.
    - PPTX: **python-pptx** — free, extracts text from every slide, speaker notes, and text boxes.
- Chunk extracted text into sections (PDF: by heading/page; PPTX: by slide) — store both raw text and structured sections.
- Store parsed output in a `parsed_submissions` table: `submission_id, raw_text, sections (JSON), source_format, parsed_at`.
- Trigger parsing automatically after upload (synchronous call is fine for now — no queue needed yet).

**Test / definition of done**

- Upload 2 PDFs (text-based and image-heavy) and 2 PPTX decks (text-heavy and image-heavy) — confirm text is extracted from all four.
- Confirm `parsed_submissions` has a row per upload with non-empty `raw_text`.
- Manually read the extracted text for one PDF and one PPTX and confirm it's not garbled or missing obvious content (e.g. slide titles).

---

### v0.3.0 — Single scoring agent (Groq-powered)

**Goal:** Prove the core loop: text in, structured score out — using a free LLM.

**Build**

- Write a hardcoded rubric (JSON): 4 criteria, e.g. `problem_fit`, `technical_depth`, `feasibility`, `innovation`, each scored 1–10.
- Set up a **Groq API** client (`groq` Python package or plain HTTP to `https://api.groq.com/openai/v1`, OpenAI-compatible). Use `llama-3.3-70b-versatile` as the default model.
- Write a single scoring call: system prompt describes the rubric, user message includes the parsed submission text, response format enforced as JSON (ask for strict JSON output; Groq's OpenAI-compatible endpoint supports `response_format: {"type": "json_object"}` on supported models — validate and retry-on-malformed as a fallback).
- Store results in a `scores` table: `submission_id, criterion, score, justification, agent_version`.
- Add a simple endpoint or script to trigger scoring for a given `submission_id`.
- Add basic retry/backoff logic for Groq's rate limits (30 RPM) — a simple `sleep` + retry wrapper is enough at this stage.

**Test / definition of done**

- Run scoring on 3 submissions with visibly different quality (one strong, one weak, one off-topic).
- Confirm the strong submission scores meaningfully higher than the off-topic one.
- Confirm every score has a non-empty justification string.
- Confirm valid JSON output across 10 consecutive runs (test for parsing failures / malformed output, and confirm your retry logic recovers from at least one induced rate-limit error).

---

## v0.3.5 — Visual content understanding (diagrams, flowcharts, architecture images)

**Goal:** Extend parsing so diagrams, flowcharts, and architecture images embedded in PDFs/PPTs aren't silently skipped — their content gets converted to text the scoring agents can actually use, while template decoration (logos, banners, theme graphics) is filtered out cheaply and reliably before ever reaching a vision model.

**Build**

- Extend the parsing agent to extract embedded images from PDFs (via **PyMuPDF**) and PPTX files (via **python-pptx**), alongside the existing text extraction.
- **Structural filter (PPTX only):** exclude images sourced from the slide master/layout (logos, background graphics, theme elements) — `python-pptx` can distinguish these from images placed directly in a slide's content area. This is a direct structural signal, not a heuristic.
- **Repetition filter (PDF, and PPTX fallback):** compute a **perceptual hash (pHash)**, via the `imagehash` library, for each remaining image. Exclude images whose pHash matches (or is near-identical to) another image appearing elsewhere in the same submission — catches repeated logos/banners even if slightly recompressed or resized between pages/slides.
- **Cross-submission caching:** maintain a cache table (`image_cache`: `phash, classification, description, cached_at`) keyed by perceptual hash. Before classifying or describing any image, check the cache first — since many teams share the same hackathon template, identical logos/banners across different teams' submissions are classified/described only once.
- **Local classification:** for images not filtered above and not already cached, run a **CLIP-based zero-shot classifier** (open-source, local, via `transformers` or `open_clip` — no API cost) with candidate labels: `["architecture diagram", "flowchart", "chart or graph", "photo", "logo or icon", "decorative graphic"]`. Capture both the top label and its confidence score.
- **Three-tier routing based on CLIP confidence:**
    - **High confidence — diagram/flowchart/chart:** send to a vision-capable model (Groq vision if available on free tier, else Google AI Studio's free Gemini tier as fallback) for a full structural description (components, connections, direction of flow).
    - **High confidence — logo/photo/decorative:** drop; no vision LLM call; store nothing.
    - **Low confidence / ambiguous:** still send to the vision LLM for a description (same as the high-confidence diagram path), but tag the result with a `needs_human_review: true` flag for later spot-check.
- Store all generated descriptions in `parsed_submissions` under a new field, `image_descriptions (JSON)`, keyed by page/slide number, including the `needs_human_review` flag where applicable. Update the cache table with the classification + description for future reuse.
- Merge image descriptions into the same structured text object used by the scoring agents (v0.3.0) — no changes needed downstream in the scoring prompts themselves.

**Test / definition of done**

- Upload a PDF and a PPTX each containing one architecture diagram with no accompanying text — confirm a description is generated and stored for that image.
- Upload a PPTX using a hackathon template with a slide-master logo — confirm it's excluded via the structural filter, with zero vision LLM calls made for it.
- Upload a PDF where the same banner image appears on every page, slightly recompressed — confirm the perceptual hash filter still catches it as repeated despite the recompression.
- Upload two different teams' submissions using the same shared template — confirm the second submission's identical template images are served from cache (no duplicate classification or vision LLM call).
- Construct or find an image that CLIP classifies with low confidence — confirm it still receives a vision LLM description AND is flagged `needs_human_review: true`.
- Confirm a submission with only decorative/template images produces an empty (or near-empty) `image_descriptions`, with no noise injected into downstream scoring.
- Confirm the system still works correctly for PDFs/PPTs with **no images at all** — `image_descriptions` should simply be empty, not error out.
- Re-run the v0.3.0 scoring agent on a submission with a diagram vs. an identical submission with a text-only description of the same architecture — confirm both produce comparable `technical_depth` scores.

> **Checkpoint — v0.4.0:** core loop demoable end to end (upload → parse → score, no UI polish needed). Pause here and make sure this is rock solid before adding complexity.

---

### v0.5.0 — Multi-agent split

**Goal:** Replace the single agent with four specialists — this is where it becomes genuinely agentic.

**Build**

- Split the single prompt into 4 agent modules, each with a narrow system prompt: `ProblemFitAgent`, `TechnicalDepthAgent`, `FeasibilityAgent`, `InnovationAgent`.
- **`TechnicalDepthAgent` scope (updated priority):** infers technical depth entirely from the PDF/PPT content — architecture diagrams described, tech stack mentioned, implementation detail in the writeup/slides. **No GitHub access required.** If a repo link happens to be present, it can be treated as a bonus signal later (see v2.5.0), not a dependency.
- Run all 4 agents in parallel (`asyncio.gather` in Python) for a given submission, respecting Groq's rate limits — stagger calls slightly if needed to stay under 30 RPM.
- Optional: use **LangGraph** (free, open-source) for orchestration if it helps structure the parallel calls — plain `asyncio` works fine too.
- Store each agent's output separately in `scores`, tagged by agent name.

**Test / definition of done**

- Run all 4 agents on the same 3 test submissions from v0.3.0.
- Confirm agents disagree in sensible ways — e.g. a technically detailed but off-theme submission should score high on `technical_depth`, low on `problem_fit`.
- Time the parallel run vs. a sequential run and confirm parallel is meaningfully faster, while staying under Groq's rate limit (check for 429 errors).
- Test a PPTX-only submission (no PDF) and confirm all 4 agents still produce sensible output.

---

### v0.6.0 — Weighted scoring + ranking

**Goal:** Turn 4 separate scores into one ranked list, with configurable weights.

**Build**

- Build a rubric config table: `hackathon_id, criterion, weight` (must sum to 1.0 or 100).
- Build a scoring engine: `composite_score = sum(criterion_score * weight)`.
- Build a ranking endpoint: given a `hackathon_id`, return all submissions sorted by `composite_score` descending.
- Add a configurable shortlist cutoff (top N, or score threshold) as a parameter.
- Add tie-breaking: if scores are equal, sort by a secondary criterion (e.g. innovation) or flag for manual review.

**Test / definition of done**

- Change rubric weights (e.g. innovation from 20% to 40%) and confirm the ranking changes accordingly.
- Confirm the ranked list updates correctly when a new submission is scored.
- Test with 2 submissions that tie exactly — confirm the tie-break rule fires instead of arbitrary ordering.
- Test cutoff at top 5 — confirm exactly 5 are marked shortlisted and the rest are not.

---

### v0.7.0 — Feedback agent + export

**Goal:** Every team gets a written rationale — this is the key differentiator vs. a spreadsheet.

**Build**

- Write a `FeedbackAgent` (Groq-powered): given all 4 criterion scores + justifications for one submission, generate a short structured response — strengths, weaknesses, one actionable suggestion, and accept/reject framing.
- Store feedback in a `feedback` table: `submission_id, strengths, weaknesses, suggestion, generated_at`.
- Build a CSV export: team name, composite score, per-criterion scores, shortlist status (Python `csv` module, free, built-in).
- Build a PDF export per team combining scores + feedback, using **ReportLab** (free, open-source — no paid PDF API needed).

**Test / definition of done**

- Generate feedback for both a shortlisted and a rejected team — confirm tone differs appropriately (encouraging for rejected, detailed for finalists).
- Confirm every feedback justification actually references something specific from that team's submission (not generic boilerplate).
- Open the exported CSV in Excel/Sheets and confirm all columns are populated correctly.
- Open the exported PDF and visually confirm it's readable and correctly formatted.

> **Milestone — v1.0.0:** usable MVP. Full pipeline works: upload (PDF/PPT) → parse → 4-agent score → rank → feedback → export. Entirely free to run. This is demo-ready and could realistically be piloted on a small hackathon at zero cost.

---

## v1.x — Team-facing polish

### v1.1.0 — Submission UX

**Goal:** Make the upload experience solid for real teams under deadline pressure.

**Build**

- Real-time validation on upload: missing sections, file too large, wrong format (only PDF/PPTX accepted) — shown before submit, not after.
- Submission status tracker (submitted → parsing → scored → shortlisted/rejected) visible to the team.
- Allow re-submission before deadline (overwrite previous version, keep history).

**Test / definition of done**

- Try uploading a corrupted PDF — confirm a clear error message, not a silent failure.
- Re-submit a file and confirm the old version is archived, not lost.
- Confirm status updates in near-real-time (polling is fine — no need for paid websocket infra) without a manual page refresh.

---

### v1.2.0 — Notifications

**Goal:** Teams should never have to ask "did it go through?"

**Build**

- Email on successful submission (confirmation + timestamp) via **Gmail SMTP** (free) or **Resend free tier** (3,000 emails/month free, no card required).
- Email reminder N hours before deadline for teams with no submission.
- Email on result publication with score breakdown + feedback attached.

**Test / definition of done**

- Submit as a test team and confirm the confirmation email arrives within a minute.
- Confirm the reminder only fires for teams without a submission, not everyone.
- Confirm the result email renders correctly on both desktop and mobile mail clients.

---

### v1.3.0 — Appeal flow

**Goal:** Give teams a structured way to contest a result.

**Build**

- Add an appeal request form (available only after results are published).
- Appeal routes to a human evaluator queue with the original AI scoring + feedback attached.
- Evaluator can respond with a final decision, logged against the submission.

**Test / definition of done**

- File a test appeal and confirm it appears in the evaluator queue with full context attached.
- Confirm a resolved appeal updates the team-facing status correctly.

---

## v2.x — Trust and safety layer

This is what turns a demo into something an organizer could actually trust for real judging. Prioritize this before v3 stretch features.

### v2.1.0 — Evaluator dashboard

**Goal:** Give human judges a working surface to review AI output.

**Build**

- Build a dashboard listing all submissions with composite score, rank, and shortlist status.
- Click into a submission to see all 4 agent scores, justifications, and generated feedback.
- Add manual override: evaluator can adjust any score with a required justification field.
- Surface any images flagged `needs_human_review: true` (from v0.3.5's low-confidence CLIP routing) in the submission detail view, alongside the original image and its generated description, so an evaluator can quickly confirm or reject whether it was classified and described appropriately.

**Test / definition of done**

- Override a score and confirm the composite score + ranking recompute immediately.
- Confirm the override justification is required — cannot save an empty reason.
- Load the dashboard with 100+ dummy submissions and confirm it stays responsive (add pagination if needed).
- Load a submission containing a `needs_human_review`-flagged image and confirm it's visibly distinguishable in the dashboard from normally-classified images (e.g. a badge or highlighted section).

---

### v2.2.0 — Audit trail

**Goal:** Every score change should be traceable — who, what, when, why.

**Build**

- Add an `audit_log` table: `submission_id, actor (AI agent name or evaluator email), field_changed, old_value, new_value, reason, timestamp`.
- Log every AI scoring event and every human override automatically.
- Build a simple audit view per submission showing the full history.

**Test / definition of done**

- Override a score twice and confirm both changes appear in order in the audit view.
- Confirm the original AI score is still visible even after multiple overrides (nothing gets destructively overwritten).

---

### v2.3.0 — Explainability

**Goal:** Every score should point back to the specific part of the submission that drove it.

**Build**

- Modify agent prompts to require a direct textual reference (quote or section/slide pointer) alongside each score.
- Display the cited excerpt next to the score in the dashboard, with a link/scroll to that part of the parsed document or slide.

**Test / definition of done**

- Spot-check 5 scores and confirm the cited excerpt is actually relevant to the score given, not a generic quote.
- Test a submission with no clearly relevant section for a criterion — confirm the agent says so rather than fabricating a citation.

---

### v2.4.0 — Prior-art / plagiarism detection (fully local, free)

**Goal:** Catch duplicate or copied submissions automatically — with zero API cost.

**Build**

- Generate embeddings locally using **Sentence-Transformers** (`all-MiniLM-L6-v2` or similar) — runs on CPU, no API calls, no cost.
- Store embeddings in **ChromaDB** (free, embedded, runs in-process — no hosted vector DB needed).
- On new submission, run a similarity search against all past + current submissions; flag matches above a threshold.

**Test / definition of done**

- Submit two near-identical documents and confirm the system flags them as similar.
- Submit two genuinely different documents on the same topic and confirm they are NOT flagged.
- Tune the similarity threshold using these two test cases until false positives are minimized.

---

### v2.5.0 — Code quality analysis _(optional / stretch — deprioritized)_

**Goal:** Give the technical depth agent a bonus signal from code, if a repo link is provided. **Not required for the system to function** — build only if time allows.

**Build**

- For submissions that _do_ include a repo link, use the free **GitHub REST API** (unauthenticated requests are free at low volume; add a free personal access token for higher limits) to pull README + file listing.
- Run lightweight static checks (e.g. basic linting) as a supplementary signal only.
- Check commit history sanity (commit count, time span) as an optional bonus flag.
- Feed this as _additional_ context into `TechnicalDepthAgent` — the agent must already work fully without it (per v0.5.0).

**Test / definition of done**

- Confirm a submission with no repo link scores identically well-formed as before (no missing-repo penalty by default).
- Test with a repo that has healthy commit history vs. one with a single last-minute commit — confirm the flag fires correctly on the latter, when present.
- Confirm a private/inaccessible repo fails gracefully with a clear message, not a crash.

---

### v2.6.0 — Bias and anomaly flagging

**Goal:** Protect against unfair or inconsistent scoring patterns.

**Build**

- Add automated checks: does composite score correlate suspiciously with team name patterns, college name, or other non-merit signals present in the text?
- Flag submissions where the 4 agents strongly disagree (high variance) for mandatory human review.
- Add a confidence field to each agent score; route low-confidence scores to human review automatically.

**Test / definition of done**

- Construct a synthetic test where team/college info is varied but content is identical — confirm scores stay consistent.
- Force high agent disagreement on a test submission and confirm it's routed to the review queue.

> **Milestone — v2.6.0** marks a genuinely trustworthy system, built entirely on free tools — this is the version worth pitching to an actual hackathon organizing body like SIH.

---

## v3.x — Scale and polish (optional stretch)

Build these only if time remains after v2.x is solid. Each is independent — pick based on what excites you most or what a specific evaluator/demo audience would value. All remain free-tier-compatible.

### v3.1.0 — Multi-track support

**Build**

- Add `hackathon_id` / `track_id` scoping to all tables.
- Rubric builder UI: drag-and-drop weight adjustment per track, add/remove criteria.
- Track selector on the evaluator dashboard.

**Test / definition of done**

- Create two tracks with different rubrics and confirm scoring/ranking is fully isolated between them.

---

### v3.2.0 — Analytics dashboard

**Build**

- Score distribution histograms per criterion (free charting: Chart.js, Recharts, or Plotly — all free/open-source).
- Criterion-wise heatmap across all teams.
- Submission funnel: registered → submitted → parsed → scored → shortlisted.

**Test / definition of done**

- Load real or dummy data for 50+ teams and confirm charts render correctly and stay readable.

---

### v3.3.0 — Live pitch evaluation

**Build**

- Accept video URL or upload; transcribe using **Whisper (open-source, run locally)** — free, no API cost, unlike paid transcription APIs.
- Feed transcript into the existing 4-agent pipeline as an additional evidence source alongside the PDF/PPT.

**Test / definition of done**

- Transcribe a 3-minute test pitch video locally and confirm transcript accuracy is usable (spot-check against the audio).
- Confirm a submission with both a PDF/PPT and a pitch video produces a combined, not duplicated, score.

---

### v3.4.0 — Team-facing Q&A chatbot

**Build**

- Chatbot (Groq-powered) scoped to a team's own submission, scores, and feedback — answers "why wasn't I shortlisted" using the stored justifications.

**Test / definition of done**

- Confirm the chatbot cannot access or leak other teams' data.
- Ask it an out-of-scope question and confirm it declines rather than hallucinating.

---

### v3.5.0 — External integrations

**Build**

- Webhook/API to sync with SIH's actual submission portal (or a generic webhook interface if no public API exists) — free, since it's just your own endpoint.
- Free Slack workspace webhook (Slack's incoming webhooks are free) or email digest of daily submission and scoring stats for organizers.

**Test / definition of done**

- Test the webhook with a mock payload and confirm data lands correctly in your system.

---

### v3.6.0 — Mobile evaluator app

**Build**

- **React Native (free/open-source)** or a PWA wrapper (free, no app-store fee needed for a PWA) around the evaluator dashboard's core views (list, detail, override).

**Test / definition of done**

- Test override flow end-to-end on an actual phone, not just a resized browser window.

---

## Suggested cadence

Since you have runway, don't rush v0.x — a shaky core makes every later version harder to trust. Spend proportionally more time on testing at the **v0.4.0** and **v1.0.0** checkpoints than on any single stretch feature in v3.x.

If you're building toward a real submission or pitch, **v2.6.0** is the strongest stopping point: it's feature-complete, trustworthy, and runs entirely on free infrastructure — a genuinely deployable pilot at zero cost. Each v3.x item beyond that is a legitimate standalone talking point if you get there.

**A note on Groq's rate limits:** the free tier (~30 RPM, ~1,000 RPD per model) is genuinely enough for building and demoing this project and even piloting it on one hackathon's worth of submissions. If you ever exceed it during heavy testing, Google AI Studio's free Gemini tier is a solid fallback with higher volume limits — worth wiring up as a secondary provider around v0.5.0 so you have redundancy for free.
