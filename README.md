# Family Budget

Multi-member household expense tracker — a family shares wallets and records
income/expense together, scoped per family.

[![CI](https://github.com/vodongha/family-budget/actions/workflows/ci.yml/badge.svg)](https://github.com/vodongha/family-budget/actions/workflows/ci.yml)

- **Backend:** FastAPI (Python 3.12) REST API
- **Database:** Oracle Autonomous Database (ADB) via `oracledb` thin mode
- **Mobile:** Flutter (Android + iOS) — *in progress*
- **Docs:** see the [Wiki](https://github.com/vodongha/family-budget/wiki) · contributor guide in [CLAUDE.md](CLAUDE.md)

---

## Features

### Backend (Phase 1 + 2 — done)

- **Auth** — register (creates a family + owner), login (JWT), `GET /auth/me`
- **Roles** — `owner` / `member`; the person who creates a family owns it
- **Invitations** — owner invites by email; the invitee accepts with a token + a
  chosen password (auto-login); owner can revoke pending invites
- **Profile & account deletion** — `PATCH /auth/me` (display name); `DELETE /auth/me`
  self-service deletion (Google Play policy): soft-delete now + scheduled 30-day purge.
  Owners must transfer ownership before deleting (sole owners tear down the whole family)
- **Wallets** — create / list / get; balance is **derived** from transactions, never stored
- **Transactions** — expense / income; positive integer amounts in đồng; family-scoped
- **Dashboard** — `GET /dashboard/summary`: total income / expense / net + per-wallet balances
- **Multi-tenant isolation** — every query is scoped by `family_id`; one family cannot see another's data
- **Health** — `GET /health` runs `SELECT 1 FROM dual` to verify the ADB connection

### Planned

Categories · multiple wallets + transfers · reports · budgets & alerts · recurring
transactions · receipt OCR · auto-categorize (merchant dictionary + Ollama). See the
roadmap in [CLAUDE.md](CLAUDE.md).

---

## Money rules (non-negotiable)

- Amounts are **integer minor units** (đồng) — never `float`. Direction comes from the
  transaction `type`, not the sign of the amount.
- Wallet balance is **derived** from the sum of transactions, never stored stale.
- Every scoped query filters by **`family_id`** (the tenant boundary).
- Identifiers: numeric `id` (internal PK, Oracle `Identity()`) + `rid` ULID (external).

---

## Tech stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI — sync routes (threadpool) |
| ORM | SQLAlchemy 2.0 (sync) |
| Database | Oracle ADB 19c (region `ap-singapore-1`), free tier |
| DB driver | `oracledb` thin mode (no Instant Client; wallet-based mTLS) |
| Migrations | Alembic (app-managed) |
| Validation | Pydantic v2 |
| Auth | OAuth2 password flow + JWT (`python-jose`); `bcrypt` hashing |
| Jobs (planned) | Celery + Celery Beat on Redis |
| Storage (planned) | MinIO (receipt images) |
| Lint / format | `ruff` |
| Types | `mypy` (strict) |
| Tests | `pytest` + SQLite in-memory |
| Containers | Docker Compose (`api` / `worker` / `beat` / `redis` / `minio`) |
| Host (planned) | Oracle Cloud Ampere A1 free tier |

---

## Project structure

```
family-budget/
├── app/
│   ├── main.py                 # FastAPI app, router registration
│   ├── core/                   # config, database (lazy engine), security, deps, celery
│   └── domains/                # one vertical slice per domain
│       ├── auth/               # register / login / me
│       ├── users/              # User + Family models, UserRole
│       ├── invitations/        # invite / accept / revoke (owner-only)
│       ├── wallets/            # wallets + derived balance
│       ├── transactions/       # expense / income
│       ├── dashboard/          # family totals
│       └── health/             # ADB connectivity probe
├── alembic/                    # migrations (env.py filters Oracle system tables)
├── tests/                      # pytest (SQLite in-memory)
├── .claude/                    # Claude Code launch config
├── .github/workflows/          # CI (ruff + pytest)
├── Dockerfile · docker-compose.yml
├── pyproject.toml · alembic.ini
└── CLAUDE.md                   # contributor / agent guide
```

Each domain follows the layering **router → service → repository → SQLAlchemy → ADB**.
See [Architecture](https://github.com/vodongha/family-budget/wiki/Architecture).

---

## Quick start

### 1. Configure

```bash
cp .env.example .env          # fill in ORACLE_PASSWORD + WALLET_PASSWORD
```

Place the unzipped ADB wallet under `./wallet/` (`ewallet.pem`, `tnsnames.ora`, ...).
**`wallet/` and `.env` are gitignored — never commit them.**

### 2. Run with Docker

```bash
docker compose up --build
curl http://localhost:8000/health        # {"status":"ok","database":true}
```

### 3. Run locally (no Docker)

```bash
python -m venv .venv && . .venv/Scripts/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
# WALLET_DIR in .env is /app/wallet (Docker); point it at the local wallet for local runs:
export WALLET_DIR="$PWD/wallet"                      # PowerShell: $env:WALLET_DIR = "$PWD\wallet"
uvicorn app.main:app --reload
```

Interactive API docs: <http://localhost:8000/docs>.

---

## Tests

```bash
pytest          # SQLite in-memory — no Oracle needed
ruff check app tests
```

Oracle-specific behaviour (sequences, `Identity`, locking) is verified against ADB
directly — see [Testing](https://github.com/vodongha/family-budget/wiki/Testing).

---

## Migrations

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Review every autogenerated migration — see
[Database & Migrations](https://github.com/vodongha/family-budget/wiki/Database-and-Migrations).

---

## Documentation

| Doc | Where |
|---|---|
| Contributor / agent guide | [CLAUDE.md](CLAUDE.md) |
| Architecture, domains, layering | [Wiki › Architecture](https://github.com/vodongha/family-budget/wiki/Architecture) |
| ADB wallet & thin-mode connection | [Wiki › Connection & Wallet](https://github.com/vodongha/family-budget/wiki/Connection-and-Wallet) |
| Alembic & Oracle gotchas | [Wiki › Database & Migrations](https://github.com/vodongha/family-budget/wiki/Database-and-Migrations) |
| Endpoint reference | [Wiki › API Reference](https://github.com/vodongha/family-budget/wiki/API-Reference) |
| Testing approach | [Wiki › Testing](https://github.com/vodongha/family-budget/wiki/Testing) |
| Git workflow & identity | [Wiki › Git Workflow](https://github.com/vodongha/family-budget/wiki/Git-Workflow) |
