"""JuryAI backend — FastAPI application entry point."""

from fastapi import FastAPI

from backend.routes import submissions

app = FastAPI(
    title="JuryAI API",
    description="Backend for the JuryAI hackathon evaluator.",
    version="0.1.0",
)

app.include_router(submissions.router)


@app.get("/health")
async def health() -> dict:
    """Simple health check."""
    return {"status": "ok"}
