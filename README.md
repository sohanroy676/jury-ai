# JuryAI

**Agentic AI hackathon evaluator** — automatically parses hackathon submissions (PDF/PPTX), scores them via four specialist AI agents, ranks and shortlists teams, and generates written feedback. Built for hackathon organizers and evaluators, with a focus on Smart India Hackathon (SIH)-style events.

> **Status:** v0.1.0 — project skeleton (upload portal + Supabase wiring). See [ROADMAP.md](ROADMAP.md) for the full plan.

## Features

- 📤 **Upload portal** — teams submit a PDF or PPTX through a Next.js frontend.
- 🗄️ **Supabase-backed** — files go to Supabase Storage, metadata to Supabase Postgres.
- 🧩 **Extensible agent pipeline** — parsing, scoring (4 agents), ranking, and feedback agents land in later versions.
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
- **v0.2.0** Parsing agent — extract text from PDF (PyMuPDF) and PPTX (python-pptx).
- **v0.3.0** Single scoring agent — Groq-powered, structured JSON output.
- **v0.4.0** Checkpoint — core loop (upload → parse → score) demoable end to end.
- **v0.5.0+** Multi-agent split, weighted scoring + ranking, feedback + export, and the v1.0.0 MVP.

See [ROADMAP.md](ROADMAP.md) and [docs/hackathon_evaluator_roadmap.md](docs/hackathon_evaluator_roadmap.md) for the full plan.

## Contributing

This project follows a strict workflow — see [.clinerules/](.clinerules/) and [AGENTS.md](AGENTS.md) for conventions around commits, testing, and code quality.

## License

Private project. All rights reserved.