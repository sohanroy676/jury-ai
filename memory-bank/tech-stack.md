# tech-stack.md

## Languages & Frameworks

**Backend + Agents:** Python (FastAPI for the API layer, plain async Python for agent orchestration)
- Chosen because the entire AI/data stack (Groq SDK, LangGraph, PyMuPDF, python-pptx, Sentence-Transformers, ChromaDB) is Python-native — keeping backend and agents in the same language avoids a cross-language boundary for no benefit.

**Frontend:** Next.js (TypeScript)

## Testing

- **Backend/agents:** `pytest`
  - Test files: `backend/tests/test_*.py`, `agents/tests/test_*.py`
  - Run: `pytest` (from repo root, or `pytest backend/` / `pytest agents/` to scope)
- **Frontend:** `Vitest`
  - Test files: colocated as `*.test.ts` / `*.test.tsx` next to the component/module they test
  - Run: `npm run test` (from `/frontend`)

## Lint / Format

- **Backend/agents:** `Ruff` (combined linter + formatter for Python)
  - Lint: `ruff check .`
  - Format: `ruff format .`
- **Frontend:** `ESLint` + `Prettier`
  - Lint: `npm run lint` (from `/frontend`)
  - Format: `npm run format` (from `/frontend`)

## Build / Run / Dev

- **Backend:** `uvicorn backend.main:app --reload` (dev), `uvicorn backend.main:app` (prod)
- **Frontend:** `npm run dev` (dev), `npm run build && npm run start` (prod)
- **Agents:** invoked internally by the backend, not run standalone in normal operation

## Database & External Services (all free-tier)

- **Database + file storage:** Supabase (free tier) — Postgres + Storage bucket for PDF/PPTX uploads
- **LLM inference:** Groq API, via the official `groq` Python package
- **Embeddings (similarity/plagiarism check):** Sentence-Transformers, run locally — no external API
- **Vector store:** ChromaDB, embedded/local — no hosted service
- **Email:** Gmail SMTP or Resend free tier (decide at implementation time)
- **Agent orchestration:** LangGraph (optional, introduced once multi-agent complexity justifies it)

All service credentials (Groq API key, Supabase URL/key, email credentials) are environment variables — never hardcoded. See `architecture.md`.