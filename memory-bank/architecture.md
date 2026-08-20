# architecture.md

## Folder Structure

Single GitHub repo (monorepo), structured as:

jury-ai/
├── frontend/ # Next.js (TypeScript) — upload portal, evaluator dashboard
│ ├── app/
│ ├── components/
│ └── tests/
├── backend/ # FastAPI — API layer, orchestrates requests to agents
│ ├── main.py
│ ├── routes/
│ ├── models/ # DB models/schemas
│ ├── services/ # Supabase client, email, export logic
│ └── tests/
├── agents/ # Agent logic — parsing, scoring, ranking, feedback
│ ├── parsing/ # PDF (PyMuPDF) + PPTX (python-pptx) extraction
│ ├── scoring/ # ProblemFitAgent, TechnicalDepthAgent, FeasibilityAgent, InnovationAgent
│ ├── ranking/
│ ├── feedback/
│ └── tests/
├── infra/ # Deployment configs, DB migrations
├── .env # ALL credentials live here — see below
└── README.md

## Data Flow

1. Team uploads a PDF or PPTX via the **frontend** upload portal.
2. Frontend calls the **backend** API directly (no separate gateway/proxy layer) to submit the file.
3. Backend uploads the file to **Supabase Storage** and inserts a `submissions` row in **Supabase Postgres**.
4. Backend triggers the **agents** layer: parsing agent extracts structured text from the file.
5. Parsed text is passed to the four scoring agents (via Groq API calls), run in parallel.
6. Scores are aggregated by the scoring engine into a composite score, then passed to the ranking agent.
7. Feedback agent generates a written rationale per submission.
8. Results (scores, rank, feedback) are written back to Supabase and served to the **frontend** evaluator dashboard and team-facing status view via the backend API.

## Key Modules

- **`frontend/`** — submission upload UI, team status tracking, evaluator dashboard (review, override, audit view).
- **`backend/`** — single source of truth API; owns all Supabase reads/writes; exposes endpoints the frontend calls directly.
- **`agents/parsing/`** — turns raw PDF/PPTX into structured text (this is the priority input path; no GitHub dependency).
- **`agents/scoring/`** — the four specialist agents; each is a narrow, independently testable module.
- **`agents/ranking/`** — weighted composite scoring + shortlist cutoff logic.
- **`agents/feedback/`** — generates per-team written rationale.
- **`infra/`** — DB migrations and any deployment configuration (Render/Vercel free tiers).

## Third-Party Services / APIs

- **Groq API** (LLM inference for all agents)
- **Supabase** (Postgres database + file storage, free tier)
- **Sentence-Transformers** (local, no API key needed)
- **ChromaDB** (local, no API key needed)
- **Email provider** (Gmail SMTP or Resend — credential TBD at implementation time)

**All credentials for the above (Groq API key, Supabase URL/service key, email credentials) live in a single `.env` file at the repo root. Keys are never hardcoded anywhere in the codebase.**