# JuryAI

**Agentic AI hackathon evaluator** — automatically parses hackathon submissions (PDF/PPTX), scores them via four specialist AI agents, ranks and shortlists teams, and generates written feedback. Built for hackathon organizers and evaluators, with a focus on Smart India Hackathon (SIH)-style events.

> **Status:** v0.6.0 — weighted scoring + ranking: configurable rubric, on-the-fly composite scores, ranked leaderboard with shortlist cutoffs. Core loop demoable end-to-end. See [ROADMAP.md](ROADMAP.md) for the full plan.

## Features

- 📤 **Upload portal** — teams submit a PDF or PPTX through a Next.js frontend.
- 📊 **Evaluator dashboard** — ranked leaderboard with shortlist badges, editable rubric weights, batch scoring of pending submissions, per-team detail pages with generated feedback, and CSV/PDF export.
- 🗄️ **Supabase-backed** — files go to Supabase Storage, metadata to Supabase Postgres.
- 🧩 **Extensible agent pipeline** — parsing, scoring (4 agents), ranking, and feedback agents.
- 💸 **100% free-tier** — no paid services, ever.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js (TypeScript), React |
| Backend | Python, FastAPI |
| Database | Supabase (Postgres) |
| File storage | Supabase Storage |
| Testing | pytest (backend), Vitest (frontend) |
| Lint/Format | Ruff (Python), ESLint + Prettier (frontend) |

## Prerequisites

- **Python 3.11+** (developed on 3.14)
- **Node.js 18+** and npm
- A free [Supabase](https://supabase.com) account (for the database + storage)

## Project Structure

```
jury-ai/
├── frontend/          # Next.js upload portal
├── backend/           # FastAPI API layer
│   ├── routes/        # API route handlers
│   ├── services/      # Supabase client, storage, DB logic
│   └── tests/         # Backend tests
├── agents/            # Agent logic (parsing, scoring, ranking, feedback) — v0.2.0+
├── infra/             # DB migrations, deployment config
├── docs/              # Setup guide, ADRs, detailed roadmap
└── memory-bank/       # Project memory (architecture, decisions, progress)
```

## Getting Started

### 1. Clone & install

```bash
git clone https://github.com/sohanroy676/jury-ai.git
cd jury-ai
```

### 2. Set up Supabase

You need a Supabase project with a `submissions` table and a `submissions` storage bucket. Follow the detailed walkthrough in **[docs/setup.md](docs/setup.md)** — it covers creating the project, running the SQL migration, and creating the bucket.

### 3. Configure environment variables

```bash
# Root: copy the example and fill in your Supabase values
cp .env.example .env
```

```bash
# Frontend: copy the example (defaults to http://localhost:8000)
cp frontend/.env.example frontend/.env.local
```

### 4. Run the backend

```bash
# From the repo root — create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

# Install dependencies into the venv
pip install -r backend/requirements.txt

# Start the backend
uvicorn backend.main:app --reload
# (Deactivate the venv when done: `deactivate`)
```

The API is now at <http://localhost:8000> — interactive docs at <http://localhost:8000/docs>.

### 5. Run the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000> and upload a PDF or PPTX.

## Demo the Core Loop (API only)

With the backend running and `.env` configured (Supabase + `GROQ_API_KEY`):

```bash
# 1. Upload a PDF or PPTX (parsed automatically on upload)
curl -s -X POST http://localhost:8000/api/submissions   -F "team_name=QuantumQuokka"   -F "file=@./proposal.pdf"
# -> {"id": "<submission_id>", "team_name": "QuantumQuokka", ...}

# 2. Trigger scoring (Groq-powered)
curl -s -X POST http://localhost:8000/api/submissions/<submission_id>/score

# 3. Read back the full record: submission + parsed text + scores
curl -s http://localhost:8000/api/submissions/<submission_id>

# 4. Configure rubric weights (fractions summing to 1.0, or percentages summing to 100)
curl -s -X PUT http://localhost:8000/api/rubrics/default   -H "Content-Type: application/json"   -d '{"weights": {"problem_fit": 0.30, "technical_depth": 0.30, "feasibility": 0.20, "innovation": 0.20}}'

# 5. Get the ranked leaderboard (shortlist top 5, or use &min_score=7.5 instead)
curl -s "http://localhost:8000/api/rankings?hackathon_id=default&top_n=5"
```

`GET /api/submissions` lists every upload, newest first. Interactive docs for all endpoints live at <http://localhost:8000/docs>.

### Batch scoring (v1.0.0)

Score every submission that lacks a complete score set in one call, one
submission at a time (stays inside Groq's free-tier rate limits). `limit`
caps how many are attempted (default 10, max 50); the response reports
per-item outcomes and how many remain.

```bash
# Score the 10 newest pending submissions
curl -s -X POST "http://localhost:8000/api/submissions/score-pending?limit=10"
# -> {"scored": 10, "failed": 0, "remaining": 12, "results": [...]}
```

## Demo the Evaluator Dashboard (browser)

With the backend and frontend running (`.env` configured with Supabase +
`GROQ_API_KEY`):

1. Open <http://localhost:3000> and upload a few PDF/PPTX submissions.
2. Open the **Evaluator dashboard** (link in the nav bar).
3. In **Score all pending**, set a batch size and click **Start batch scoring** —
   the leaderboard below populates as submissions get scored.
4. Tune **Rubric weights (%)** and save — the leaderboard recomputes immediately.
5. Export the board via **Export CSV**.
6. Click a team name to open its detail page: read criterion scores and
   justifications, generate written feedback (verdict follows the shortlist
   cutoff `top N` you set), and **Download PDF report**.

## Testing

```bash
# Backend (from repo root) — ensure the venv is active first
venv\Scripts\pytest     # Windows
# source venv/bin/activate && pytest   # macOS/Linux

# Frontend (from /frontend)
npm run test
```

## Lint & Format

```bash
# Backend (from repo root) — ensure the venv is active first
venv\Scripts\ruff check .      # lint   (Windows)
venv\Scripts\ruff format .     # format (Windows)
# source venv/bin/activate && ruff check . / ruff format .   # macOS/Linux

# Frontend (from /frontend)
npm run lint        # lint
npm run format      # format
```

## Roadmap

- **v0.1.0** ✅ Project skeleton — upload portal, Supabase DB + storage wired.
- **v0.2.0** ✅ Parsing agent — extract text from PDF (PyMuPDF) and PPTX (python-pptx).
- **v0.3.0** ✅ Single scoring agent — Groq-powered, structured JSON output.
- **v0.4.0** ✅ Checkpoint — core loop (upload → parse → score) demoable end to end.
- **v0.5.0** ✅ Multi-agent split — four specialist agents (problem fit, technical depth, feasibility, innovation) score in parallel; technical depth inferred from document content only.
- **v0.6.0** ✅ Weighted scoring + ranking — configurable rubric (`PUT /api/rubrics/{hackathon_id}`), composite leaderboard (`GET /api/rankings`), top-N / min-score shortlist cutoffs, deterministic tie-breaking.
- **v0.7.0+** Feedback agent + export, and the v1.0.0 MVP.

See [ROADMAP.md](ROADMAP.md) and [docs/hackathon_evaluator_roadmap.md](docs/hackathon_evaluator_roadmap.md) for the full plan.

## Contributing

This project follows a strict workflow — see [.clinerules/](.clinerules/) and [AGENTS.md](AGENTS.md) for conventions around commits, testing, and code quality.

## License

Private project. All rights reserved.