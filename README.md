# Family Budget

Multi-member household expense tracker.

- **Backend:** FastAPI (Python 3.12) · SQLAlchemy 2.0 · Alembic · Pydantic v2
- **Database:** Oracle Autonomous Database (ADB) via `python-oracledb` (thin mode, wallet)
- **Auth:** OAuth2 password flow + JWT (`python-jose` + `passlib`/bcrypt)
- **Jobs / cache:** Celery + Celery Beat · Redis
- **Storage:** MinIO (receipt images, from v1.7)
- **Mobile:** Flutter (Android + iOS) — separate repo / `mobile/` later
- **Host:** Oracle Cloud Ampere A1 (free tier), all containers

Architecture mirrors a layered service design: **router → service → repository**.

## Money rules (non-negotiable)

- Amounts are stored as **integer minor units** (đồng). **Never `float`.** Oracle `NUMBER(15)`.
- Wallet balance is **derived** from the sum of transactions (or updated inside a DB
  transaction using `SELECT ... FOR UPDATE`). Never stored as a stale denormalized value.
- Every query is **scoped by `family_id`** via the `get_current_family` dependency
  (the multi-tenant boundary). Repositories always take `family_id`.
- Identifiers: numeric `id` (PK) + `rid VARCHAR2(26)` holding a **ULID** for external use.

## Phase 1 scope (this scaffold)

Vertical slice: connect FastAPI → Oracle ADB → JWT auth → one family → one wallet →
expense/income transactions → dashboard total.

Right now the scaffold contains the **connection spike + auth skeleton**:

- `GET /health` → runs `SELECT 1 FROM dual` against ADB (the riskiest infra step)
- `POST /auth/login` / `GET /auth/me`
- `User` + `Family` models, Alembic baseline

## Local run

```bash
# 1. Copy env template and fill in ADB wallet details
cp .env.example .env

# 2. Place the unzipped Oracle ADB wallet under ./wallet/ (cwallet.sso, tnsnames.ora, ...)

# 3. Bring up the stack
docker compose up --build

# 4. Verify infra
curl http://localhost:8000/health
```

Without Docker:

```bash
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

## Tests

```bash
pytest
```

Pure logic (balance, budget, validation) is tested against SQLite in-memory for speed;
Oracle-specific behaviour (sequences, Oracle Text) is tested against Oracle XE / a test
schema on ADB in CI.

## Migrations

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```
