"""FastAPI application entry point."""

from fastapi import FastAPI

from app.core.config import settings
from app.domains.auth.router import router as auth_router
from app.domains.dashboard.router import router as dashboard_router
from app.domains.health.router import router as health_router
from app.domains.transactions.router import router as transactions_router
from app.domains.wallets.router import router as wallets_router

app = FastAPI(
    title="Family Budget",
    version="0.1.0",
    description="Multi-member household expense tracker — Phase 1 vertical slice.",
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(wallets_router)
app.include_router(transactions_router)
app.include_router(dashboard_router)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {"app": "family-budget", "env": settings.env}
