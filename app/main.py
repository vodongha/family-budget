"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.domains.auth.router import router as auth_router
from app.domains.dashboard.router import router as dashboard_router
from app.domains.health.router import router as health_router
from app.domains.invitations.router import router as invitations_router
from app.domains.stats.router import router as stats_router
from app.domains.transactions.router import router as transactions_router
from app.domains.wallets.router import router as wallets_router

app = FastAPI(
    title="Family Budget",
    version="0.1.0",
    description="Multi-member household expense tracker — Phase 1 vertical slice.",
)

# CORS — the Flutter web client runs on a different origin and calls this API
# from the browser. Auth uses a Bearer token (no cookies), so allowing all
# origins is safe here; tighten to specific origins for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(invitations_router)
app.include_router(wallets_router)
app.include_router(transactions_router)
app.include_router(dashboard_router)
app.include_router(stats_router)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {"app": "family-budget", "env": settings.env}
