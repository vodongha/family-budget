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

- **Auth** — register (creates a family + owner), login (JWT), `GET /auth/me`; optional
  **phone** (E.164, validated with `phonenumbers`, unique)
- **Sign in with Google** — `POST /auth/google` verifies a Google ID token, links it to
  an existing email or creates a new family; Google is unlinked on account deletion
- **Roles & members** — `owner` / `member`; the family creator owns it. `GET /members`
  lists the family; `POST /families/transfer-ownership` hands ownership to another member
  (single-owner — the old owner becomes a member)
- **Invitations** — owner invites by **email or phone**. A new contact gets a public invite
  link (accept with a chosen password → auto-login). A contact that **already has an account**
  gets an **in-app invite** (`GET /invitations/inbox` → `POST /invitations/{rid}/accept-existing`
  / `decline`) and is moved into the family in one tap, with consent — no link. Owner can revoke
- **Statistics** — `GET /stats/monthly` (per-month income/expense) + `GET /stats/by-category`
  (totals per category); both scope-aware (personal / family)
- **Profile & account deletion** — `PATCH /auth/me` (display name + phone); `DELETE /auth/me`
  self-service deletion (Google Play policy): soft-delete now + scheduled 30-day purge.
  Owners must transfer ownership before deleting (sole owners tear down the whole family)
- **Wallets** — **family** (shared) or **personal** (private to creator); create / list / get /
  **delete** (cascades its transactions); balance is **derived**, never stored. `?scope=` filters
- **Categories** — family-scoped income/expense labels (emoji + colour) for tagging transactions
- **Transactions** — expense / income; positive integer đồng; optional category; family-scoped.
  Create / list (filter by `type`, `category_rid`, `date_from/to`) / **edit** / **delete**
- **Budgets** — per-category **monthly limit** with current-month spend (`GET/POST/PATCH/DELETE /budgets`)
- **Transfers** — move money between wallets via linked `transfer_in`/`transfer_out` legs
  (`POST /transfers`, `DELETE /transfers/{group_rid}`); excluded from income/expense totals
- **Dashboard** — `GET /dashboard/summary`: total income / expense / net + per-wallet balances
- **Multi-tenant isolation** — every query is scoped by `family_id`; one family cannot see another's data
- **Privacy policy** — `GET /privacy?lang=vi|en` serves a public, bilingual HTML page (the
  Google Play store-listing URL; also embedded in-app via a WebView)
- **Health** — `GET /health` runs `SELECT 1 FROM dual` to verify the ADB connection

### Planned

Per-member spending reports · budget alerts · recurring transactions · receipt OCR ·
auto-categorize (merchant dictionary + Ollama). See the roadmap in [CLAUDE.md](CLAUDE.md).

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
| Auth | OAuth2 password flow + JWT (`python-jose`); `bcrypt` hashing; Google ID token (`google-auth`) |
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
│       ├── auth/               # register / login / me / google / profile / delete
│       ├── account/            # scheduled purge of soft-deleted accounts
│       ├── users/              # User + Family models, UserRole
│       ├── invitations/        # invite by email/phone, public accept, revoke
│       ├── wallets/            # wallets + derived balance
│       ├── transactions/       # expense / income
│       ├── dashboard/          # family totals
│       ├── stats/              # monthly income/expense aggregation
│       ├── legal/              # public bilingual privacy policy (HTML)
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
# Optional — enables Sign in with Google (must match the client used by the app):
export GOOGLE_CLIENT_ID="...apps.googleusercontent.com"
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

---

## License

[MIT](LICENSE)

---

## Built with

[Claude Code](https://claude.ai/code) by Anthropic. 🤖
