"""JuryAI backend — FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.routes import appeals, export, feedback, ranking, scoring, submissions
from version import APP_VERSION

app = FastAPI(
    title="JuryAI API",
    description="Backend for the JuryAI hackathon evaluator.",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    # Frontend origins come from FRONTEND_URL (comma-separated) via Settings,
    # which also feeds notification-email links (v1.2.0).
    allow_origins=settings.frontend_urls,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(submissions.router)
app.include_router(scoring.router)
app.include_router(ranking.router)
app.include_router(feedback.router)
app.include_router(export.router)
app.include_router(appeals.router)


@app.get("/health")
async def health() -> dict:
    """Simple health check."""
    return {"status": "ok"}
