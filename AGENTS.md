# AGENTS.md

## Project Overview
JuryAI is an agentic AI system that parses hackathon submissions (PDF/PPTX), scores them via four specialist AI agents, ranks and shortlists teams, and generates written feedback — automatically.

## Tech Stack
Python (FastAPI + agent orchestration) + Next.js (TypeScript) frontend, Supabase (DB + storage), Groq API for LLM inference — all free-tier.

## Commands
- Backend dev: `uvicorn backend.main:app --reload`
- Frontend dev: `npm run dev` (from `/frontend`)
- Backend test: `pytest`
- Frontend test: `npm run test` (from `/frontend`)
- Backend lint/format: `ruff check .` / `ruff format .`
- Frontend lint/format: `npm run lint` / `npm run format` (from `/frontend`)

## Critical Conventions
- Never hardcode API keys or credentials — everything goes in the root `.env` file.
- Only free-tier services and APIs are permitted anywhere in this project — no paid dependencies.
- PDF and PPTX are the priority input formats; do not build features that assume a GitHub repo is present or required.
- Keep the four scoring agents (`agents/scoring/`) as independent, narrowly-scoped modules — don't collapse them back into a single prompt.

See `.clinerules/` for detailed project rules.