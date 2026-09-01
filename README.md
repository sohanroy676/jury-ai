# JuryAI

**Agentic AI hackathon evaluator** — automatically parses hackathon submissions (PDF/PPTX), scores them via four specialist AI agents, ranks and shortlists teams, and generates written feedback. Built for hackathon organizers and evaluators, with a focus on Smart India Hackathon (SIH)-style events and multi-track competitions.

> **Status:** v3.2.0 — Multi-Track Scoping, Analytics Dashboard & Modern Dark Glassmorphism UI: track creation and scoping (`/dashboard/tracks`), analytics suite with score distributions, criterion heatmaps & submission funnel (`/dashboard/analytics`), cited excerpts for explainability, manual score overrides with provenance tracking, appeals queue (`/dashboard/appeals`), dual-transport email notifications (`EMAIL_PROVIDER=smtp|resend`), batch scoring, and CSV/PDF export. See [ROADMAP.md](ROADMAP.md) and [docs/explanation.md](docs/explanation.md) for full details.

---

## 🌟 Key Features

- 📤 **Upload Portal** — Teams submit PDF or PPTX pitch decks with inline validation, team email collection, and duplicate re-submission replacement flow (`409 Conflict`).
- 🎛️ **Multi-Track Scoping** — Create hackathon tracks (e.g. AI/ML, Hardware, FinTech) with custom rubric weightings (`PUT /api/rubrics/{trackId}`) and track-scoped leaderboards.
- 🎯 **Four Specialist AI Agents** — Problem Fit, Technical Depth, Feasibility, and Innovation agents score concurrently in parallel via Groq LLM inference (`llama-3.3-70b-versatile`).
- 💬 **Explainability & Cited Excerpts** — Every AI score includes a direct quoted excerpt from the team's presentation as empirical evidence.
- 📊 **Analytics Dashboard** — Visual score distribution histograms, criterion performance heatmaps, and pipeline submission funnels (`/dashboard/analytics`).
- ✏️ **Manual Overrides with Provenance** — Evaluators can override any score with a required justification; original AI scores are preserved and rankings instantly update.
- 📩 **Appeals & Resolution Queue** — Teams file appeals post-results; evaluators review team submissions, AI scores, and written feedback in a dedicated queue (`/dashboard/appeals`) with automated resolution emails.
- 🎨 **Modern Dark Glassmorphism Design System** — Built with Google Fonts (`Outfit`, `Inter`, `JetBrains_Mono`), HSL gradient progress fills, sticky `sessionStorage` track selection, and quiet polling.
- ✉️ **Dual-Transport Email Notifications** — Automatic submission confirmation and results-with-feedback emails via Gmail SMTP or Resend API.
- 📑 **CSV & PDF Report Export** — Track-scoped leaderboard CSV downloads and ReportLab PDF evaluation reports for individual teams.
- 💸 **100% Free-Tier Architecture** — Operates completely on free-tier services (Groq API, Supabase Postgres & Storage, standard Python smtplib).

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Next.js 15 (TypeScript), React 19, Recharts |
| **Backend API** | Python 3.14 / FastAPI, Pydantic, ASGI |
| **Database & Storage** | Supabase (Postgres & Object Storage) |
| **LLM & Vision** | Groq API (`llama-3.3-70b-versatile`) + Gemini / Groq Vision |
| **PDF Report Generation** | ReportLab |
| **Testing** | `pytest` (Backend - 432 tests) & `Vitest` (Frontend - 52 tests) |
| **Linting & Code Quality** | Ruff (Python), ESLint + Prettier (Frontend) |

---

## 📁 Project Structure

```
jury-ai/
├── frontend/          # Next.js 15 App Router frontend (TypeScript)
│   ├── app/           # Portal, Dashboard, Analytics, Tracks, Appeals pages
│   ├── components/    # Reusable UI components & TrackSelector
│   └── lib/           # Typed API client (api.ts) & Vitest tests
├── backend/           # FastAPI backend
│   ├── routes/        # Submissions, Scores, Rankings, Rubrics, Analytics, Appeals, Tracks, Export
│   ├── services/      # Supabase DB & Storage services, Email dispatcher
│   └── tests/         # Pytest backend test suite (432 tests)
├── agents/            # AI Agent system
│   ├── parsing/       # PDF/PPTX text extraction & Vision router
│   ├── scoring/       # Four specialist agents (Problem Fit, Tech Depth, Feasibility, Innovation)
│   ├── ranking/       # Weighted composite ranking engine & tie-breaker
│   └── feedback/      # Written feedback generator agent
├── infra/             # Supabase SQL migrations (0001 - 0012)
├── docs/              # Setup guide, Architecture, ADRs, Project Explanation (`docs/explanation.md`)
└── memory-bank/       # Active context, architecture patterns, progress logs
```

---

## 🚀 Quick Start Guide

### 1. Clone the Repository

```bash
git clone https://github.com/sohanroy676/jury-ai.git
cd jury-ai
```

### 2. Set Up Supabase Database & Bucket

Follow the step-by-step instructions in **[docs/setup.md](docs/setup.md)** to set up your free Supabase project, execute SQL migrations (`infra/migrations/`), and create the `submissions` storage bucket.

### 3. Configure Environment Variables

```bash
# Copy root .env template
cp .env.example .env

# Copy frontend .env.local template
cp frontend/.env.example frontend/.env.local
```

Fill in your `SUPABASE_URL`, `SUPABASE_KEY`, `GROQ_API_KEY`, and optional email SMTP/Resend credentials in `.env`.

### 4. Run the Backend (FastAPI)

```bash
# Create and activate Python virtual environment
python -m venv venv

# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Start FastAPI dev server
uvicorn backend.main:app --reload
```
- API Endpoint: <http://localhost:8000>
- Interactive Swagger Docs: <http://localhost:8000/docs>

### 5. Run the Frontend (Next.js)

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```
- Open <http://localhost:3000> in your browser to access the JuryAI submission portal and evaluator dashboard.

---

## 🧪 Testing & Code Quality

```bash
# Run backend pytest suite (432 tests)
pytest --ignore=agents/tests/test_image_classify.py

# Run frontend Vitest suite (52 tests)
cd frontend
npm run test

# Check code linting
ruff check .           # Backend
npm run lint           # Frontend
```

---

## 📘 Comprehensive Documentation

For an in-depth walkthrough of the AI multi-agent architecture, data flows, database schemas, and free-tier strategy, refer to:
- 📖 **[docs/explanation.md](docs/explanation.md)** — Detailed project explanation and presentation guide.
- ⚙️ **[docs/setup.md](docs/setup.md)** — Production setup and database migration guide.
- 🗺️ **[ROADMAP.md](ROADMAP.md)** — Complete version release history and future feature plans.

---

## 📄 License

Private project. All rights reserved.