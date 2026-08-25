"""JuryAI backend — FastAPI application entry point."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import export, feedback, ranking, scoring, submissions
from version import APP_VERSION

# Allowed frontend origins (comma-separated in FRONTEND_URL env var).
# Defaults to the local dev frontend.
_frontend_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_URL", "http://localhost:3000").split(",")
    if origin.strip()
]

app = FastAPI(
    title="JuryAI API",
    description="Backend for the JuryAI hackathon evaluator.",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(submissions.router)
app.include_router(scoring.router)
app.include_router(ranking.router)
app.include_router(feedback.router)
app.include_router(export.router)


@app.get("/health")
async def health() -> dict:
    """Simple health check."""
    return {"status": "ok"}
