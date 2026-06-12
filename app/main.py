"""FastAPI application entry point."""

from fastapi import FastAPI

from app.core.config import settings
from app.domains.auth.router import router as auth_router
from app.domains.health.router import router as health_router

app = FastAPI(
    title="Family Budget",
    version="0.1.0",
    description="Multi-member household expense tracker — Phase 1 vertical slice.",
)

app.include_router(health_router)
app.include_router(auth_router)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {"app": "family-budget", "env": settings.env}
