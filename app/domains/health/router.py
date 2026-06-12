"""Health checks. /health runs SELECT 1 FROM dual against ADB — the infra spike
that de-risks the wallet + thin-mode connection before any feature is built.
"""

from fastapi import APIRouter
from sqlalchemy import text

from app.core.deps import SessionDep

router = APIRouter(tags=["health"])


@router.get("/health")
def health(session: SessionDep) -> dict[str, object]:
    db_ok = False
    error: str | None = None
    try:
        result = session.execute(text("SELECT 1 FROM dual")).scalar()
        db_ok = result == 1
    except Exception as exc:  # noqa: BLE001 — surface any connection failure to caller
        error = str(exc)
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "error": error}
