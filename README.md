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

- **Auth** — register an **account** (login + `GET /auth/me`); the account joins or creates a
  family afterwards, so registration no longer forces a family up front (`family_name` optional —
  pass it to create+own a family in one step). `POST /families` creates a family and makes you its
  owner. `POST /auth/change-password` changes the password — or **sets the first one** for a
  Google-only account. Optional **phone** (E.164, validated with `phonenumbers`, unique)
- **Sign in with Google** — `POST /auth/google` verifies a Google ID token and links it to an
  existing account by email (**case-insensitive**, so the same person stays one account); a brand-new
  Google account starts with no family (creates/joins one after sign-in). Google is unlinked on
  account deletion
- **Personal works without a family** — `wallets`/`transactions` `family_id` is nullable; a
  **personal** wallet is owned by the user (no family needed). A family is created on demand
  (`POST /families`); the family scope (shared wallets) requires one. Reads use `OptionalFamily`.
- **Roles, members & family management** — `owner` / `member`. `GET /members` lists the family;
  `POST /families/transfer-ownership` hands ownership to another member; `PATCH /families` renames;
  `DELETE /families` deletes it (owner, sole member — keeps personal data); `POST /families/leave`
  leaves; `DELETE /families/members/{rid}` removes a member (owner). Membership changes return a
  fresh JWT
- **Invitations** — **any family member** invites by **email or phone** (the invitee always joins
  as a member). A new contact gets a public invite link (accept with a chosen password →
  auto-login). A contact that **already has an account** gets an **in-app invite**
  (`GET /invitations/inbox` → `POST /invitations/{rid}/accept-existing` / `decline`) and is moved
  into the family in one tap, with consent — no link. Owner can revoke
- **Statistics** — `GET /stats/monthly` (per-month income/expense) + `GET /stats/by-category`
  (totals per category); both scope-aware (personal / family)
- **Profile & account deletion** — `PATCH /auth/me` (display name + phone); `DELETE /auth/me`
  self-service deletion (Google Play policy): soft-delete now + scheduled 30-day purge.
  Owners must transfer ownership before deleting (sole owners tear down the whole family)
- **Wallets** — **family** (shared) or **personal** (private to creator), each with an optional
  **icon + colour**; create / list / get / **edit** (`PATCH /wallets/{rid}` — rename/icon/colour) /
  **delete** (cascades its transactions); balance is **derived**, never stored. `?scope=` filters.
  Edit a family wallet as the owner, a personal wallet as its owner
- **Categories** — family-scoped income/expense labels (emoji + colour) for tagging transactions;
  rename + change icon/colour (`PATCH /categories/{rid}`)
- **Transactions** — expense / income; positive integer đồng; optional category; family-scoped.
  Create / list (filter by `type`, `category_rid`, `date_from/to`) / **edit** / **delete**
- **Budgets** — per-category **monthly limit** with current-month spend (`GET/POST/PATCH/DELETE /budgets`)
- **Transfers** — move money between wallets via linked `transfer_in`/`transfer_out` legs
  (`POST /transfers`, `DELETE /transfers/{group_rid}`); excluded from income/expense totals
- **Dashboard** — `GET /dashboard/summary`: total income / expense / net + per-wallet balances
- **Currencies & exchange rates** — each wallet has its own ISO-4217 currency; per-wallet figures
  stay in it, while cross-wallet **totals** (dashboard / stats / budgets) convert to a chosen
  **display currency** via `?display_currency=` (default base VND) using stored rates. Rates refresh
  every 12h (Celery beat) from a free public source; `GET /rates` reports when they were last
  updated and `POST /rates/refresh` pulls a fresh set on demand. Transfers must share a currency
- **Multi-tenant isolation** — every query is scoped by `family_id`; one family cannot see another's data
- **Privacy policy** — `GET /privacy?lang=vi|en` serves a public, bilingual HTML page (the
  Google Play store-listing URL; also embedded in-app via a WebView)
- **Admin panel** — a server-rendered, super-admin-only console at `/admin` (session cookie,
  separate from the API JWT and the web app). Responsive (collapsible grouped icon sidebar →
  drawer on mobile); tables are datatables (sort + search + pagination). Dashboard, **user
  management** (create / edit / **soft-delete** [flag only, data kept] / restore / reset password /
  unlink Google) and **transaction
  CRUD** per wallet + a global transactions view, **family management**
  (rename / soft-delete / restore, members + wallets, and category & budget CRUD), and
  wallet rename/delete, and an Ops **Dependencies** panel (GitHub Dependabot alerts for both repos). Admin transaction writes reuse the app's
  money logic (integer minor units, derived balances); transfers are delete-only. Admins are
  bootstrapped with `python -m app.scripts.create_admin` — never via the public API
- **Health** — `GET /health` runs `SELECT 1 FROM dual` to verify the ADB connection

### Planned

Per-member spending reports · budget alerts · recurring transactions · receipt OCR ·
auto-categorize (merchant dictionary + Ollama). See the roadmap in [CLAUDE.md](CLAUDE.md).

---

## Money rules (non-negotiable)

- Amounts are **integer minor units** of the wallet's own currency — never `float`. Direction
  comes from the transaction `type`, not the sign of the amount.
- Cross-wallet totals are converted to a single currency (base, or the request's display currency);
  **never sum raw minor units across currencies.**
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

## Deploy (Fly.io)

Auto-deploys to Fly.io on every push to `master` via
[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) (runs ruff + pytest, then
`flyctl deploy`). The app runs two process groups from one image — `app` (FastAPI, HTTP) and
`worker` (Celery worker with embedded beat for the daily purge job); see [`fly.toml`](fly.toml).
The ADB wallet is **never** committed — it is materialised from base64 secrets at startup by
[`scripts/fly_entrypoint.sh`](scripts/fly_entrypoint.sh).

**One-time setup:**

```bash
fly apps create famo                       # must match `app` in fly.toml
fly redis create                               # Upstash Redis → gives a REDIS_URL

# App secrets:
fly secrets set \
  ORACLE_PASSWORD=... WALLET_PASSWORD=... \
  JWT_SECRET="$(openssl rand -hex 32)" \
  ADMIN_SESSION_SECRET="$(openssl rand -hex 32)" \
  GOOGLE_CLIENT_ID="...apps.googleusercontent.com" \
  REDIS_URL="rediss://...upstash..." --app famo

# Optional — powers the admin Dependencies panel (GitHub Dependabot alerts):
fly secrets set GITHUB_TOKEN="ghp_..." --app famo

# Wallet files as base64 secrets (values stay local, never printed):
fly secrets set \
  WALLET_EWALLET_PEM_B64="$(base64 -w0 wallet/ewallet.pem)" \
  WALLET_TNSNAMES_B64="$(base64 -w0 wallet/tnsnames.ora)" \
  WALLET_SQLNET_B64="$(base64 -w0 wallet/sqlnet.ora)" --app famo

# Custom domain + TLS:
fly certs add famo.io.vn --app famo        # then add the shown A/AAAA (or CNAME) DNS records

# CI deploy token → add as the GitHub repo secret FLY_API_TOKEN:
fly tokens create deploy --app famo
```

`ENV` and `WALLET_DIR` come from `fly.toml`; everything secret comes from `fly secrets`. Tighten
`CORSMiddleware` in `app/main.py` to the web client's real origin for production.

**Bootstrap the first admin** (once, after the admin migration has deployed):

```bash
fly ssh console -a famo -C \
  "python -m app.scripts.create_admin --email you@example.com --name 'Your Name'"
# Set ADMIN_PASSWORD in the machine env first, or run without -C for the interactive prompt.
```

The `/admin` console is then reachable at `https://famo.io.vn/admin`.

---

## License

[MIT](LICENSE)

---

## Built with

[Claude Code](https://claude.ai/code) by Anthropic. 🤖
