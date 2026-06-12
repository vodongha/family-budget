# Family Budget — CLAUDE.md

## Project overview

Multi-member household expense tracker. A family shares wallets and records income/expense
together; every member sees the same data, scoped to their family. Multi-tenant by `family_id`.

- **Repo:** https://github.com/vodongha/family-budget (private; renamed from `htford`, git history preserved)
- **Backend:** FastAPI (Python) REST API
- **Mobile:** Flutter (Android + iOS) — separate workspace / `mobile/` later
- **Host (planned):** Oracle Cloud Ampere A1 free tier, all containers
- **Status:** Phase 1 — connection spike + auth skeleton landed and verified against live ADB.

The architecture deliberately mirrors a layered service design (the author's day-job pattern):
**router → service → repository**. Keep that separation; it is the backbone of the project.

## Technology stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 (Docker image). Local dev venv may be 3.11 — keep code 3.12-compatible |
| Web framework | FastAPI — sync routes (FastAPI runs them in a threadpool; plenty for this workload) |
| ORM | SQLAlchemy 2.0 (sync). Async Oracle is young — do not adopt without a measured reason |
| DB | Oracle Autonomous Database (ADB), 19c, region `ap-singapore-1`. Free 20 GB |
| DB driver | **`oracledb`** thin mode (no Oracle Instant Client needed). Connects to ADB via wallet (mTLS) |
| Migrations | Alembic. App-managed; **never** rely on auto-create. Connection comes from `app.core.config` (no URL in `alembic.ini`) |
| Validation / DTOs | Pydantic v2 — the type shield at every API boundary (critical for money code) |
| Auth | OAuth2 password flow + JWT (`python-jose`). Passwords hashed with **`bcrypt`** (the library, directly) |
| Background jobs | Celery + Celery Beat (broker/backend on Redis) — schedules land from the budget/recurring phases |
| Cache / broker | Redis |
| File storage | MinIO (receipt images, from the OCR phase) |
| OCR (planned) | `pytesseract` — receipt hints, never the source of truth |
| AI (planned) | Ollama via `httpx` — only for merchant cases the dictionary misses |
| Search (planned) | Oracle Text (built into ADB) — no Elasticsearch |
| Lint / types | `ruff` (lint + import order) + `mypy` (strict) |
| Tests | `pytest` + SQLite in-memory for pure logic; Oracle-specific behaviour tested separately |
| Containers | Docker Compose: `api`, `worker`, `beat`, `redis`, `minio` |

## Money rules (non-negotiable)

This app moves real household money. These rules are not style preferences.

- **Amounts are integer minor units** (đồng). **Never `float`.** Oracle `NUMBER(15)`, Python `int`,
  enforced by Pydantic at the boundary.
- **Wallet balance is derived** from the sum of its transactions — or updated inside a DB
  transaction with `SELECT ... FOR UPDATE`. Never store a stale denormalized balance.
- **Every scoped query filters by `family_id`.** This is the tenant boundary. Repositories always
  receive `family_id` explicitly; services never hold it as state. Enforced via the
  `get_current_family` FastAPI dependency (see Architecture).
- **`transfer` (wallet-to-wallet) is deferred to v1.1.** MVP is expense/income only.
- If you touch balance computation, transaction writes, or the `family_id` scope, **write a test**
  before you change behaviour. A wrong write at family scale is worse than a slow feature.

## Identifiers

- Numeric `id` — internal primary key. **On Oracle this MUST be declared `Identity()`**
  (`mapped_column(Identity(), primary_key=True)`). Without it Oracle raises `ORA-01400` on insert
  (SQLite auto-increments silently, so tests pass while Oracle fails — see Gotchas).
- `rid VARCHAR2(26)` — a **ULID** (`python-ulid`), the external/public identifier. Expose `rid` in
  APIs and JWT subjects, never the numeric `id`.

## Project structure

Domain-oriented. Each domain owns its full vertical slice.

```
family-budget/
├── app/
│   ├── main.py                  # FastAPI app, router registration
│   ├── core/
│   │   ├── config.py            # pydantic-settings — env / .env, wallet paths, JWT, Redis
│   │   ├── database.py          # SQLAlchemy Base + LAZY engine (get_engine) + get_session dep
│   │   ├── security.py          # bcrypt hashing + JWT create/decode
│   │   ├── deps.py              # SessionDep, CurrentUser, CurrentFamily (tenant scope)
│   │   └── celery_app.py        # Celery app (Redis broker)
│   └── domains/
│       ├── users/
│       │   └── models.py        # User + Family ORM models
│       ├── auth/
│       │   ├── router.py        # thin: parse request, delegate, shape response
│       │   ├── service.py       # business logic, stateless (session passed in)
│       │   ├── repository.py    # DB access only — no business logic
│       │   └── schemas.py       # Pydantic DTOs
│       └── health/
│           └── router.py        # GET /health → SELECT 1 FROM dual (ADB connectivity probe)
├── alembic/
│   ├── env.py                   # reuses app engine; include_name filters Oracle system tables
│   └── versions/                # migration scripts
├── tests/
│   ├── conftest.py              # SQLite in-memory engine; overrides get_session
│   ├── test_auth.py
│   └── test_health.py
├── Dockerfile                   # python:3.12-slim, pip install -e .
├── docker-compose.yml           # api / worker / beat / redis / minio
├── pyproject.toml               # deps + ruff + mypy + pytest config
├── alembic.ini
├── .env.example                 # template — placeholders only, no real secrets
├── .env                         # real config — GITIGNORED, never commit
└── wallet/                      # ADB wallet — GITIGNORED, never commit
```

### Planned domains (not yet built)

`wallets`, `categories`, `transactions`, `budgets`, `reports`, `ocr`, `ai`. Each follows the same
`router / service / repository / schemas / models (/ tasks for Celery)` layout.

## Architecture & conventions

### Layered, like the day-job stack

```
router → service → repository → SQLAlchemy → Oracle ADB
```

- **Routers are thin.** Parse the request, pull `CurrentUser` / `CurrentFamily` from dependencies,
  delegate to a service, shape the response. No business logic.
- **Services are stateless.** They receive the `Session` and `family_id` per call — never store
  tenant context. Business logic lives here.
- **Repositories are DB-only.** Read/write queries; always scoped by `family_id` for tenant data.

### Tenant scope — `get_current_family`

`app/core/deps.py` exposes `CurrentFamily` (an `int family_id` resolved from the JWT/user). This is
the equivalent of a tenant key. Pass it into every service/repository call that reads or writes
family-owned data. Treat a query without a `family_id` filter on tenant tables as a bug.

### Lazy database engine

`app.core.database.get_engine()` builds the Oracle engine **on first use**, not at import time.
This keeps importing the app free of an Oracle-driver requirement, so the SQLite test suite runs
without `oracledb` and the real connection only opens when a request needs it. Don't move engine
creation back to module top level.

### Async

Currently sync end-to-end on purpose (FastAPI threadpool + SQLAlchemy sync). If async is ever
adopted it must be all the way down — no sync-over-async, no mixing. Until then, keep it simple.

## Connection & wallet — ADB via oracledb thin mode

Thin mode talks to ADB over mTLS using the downloaded wallet. It reads **`ewallet.pem`** and
decrypts it with the **wallet password** (set when downloading the wallet). It does **not** use
`cwallet.sso` (that's for thick mode / other clients).

`app/core/database.py` passes to the driver:

| connect arg | source (`.env`) |
|---|---|
| `user` | `ORACLE_USER` (`ADMIN`) |
| `password` | `ORACLE_PASSWORD` |
| `dsn` | `ORACLE_DSN` — a TNS alias from `wallet/tnsnames.ora` (e.g. `vodongha_tp`, the OLTP service) |
| `config_dir` + `wallet_location` | `WALLET_DIR` |
| `wallet_password` | `WALLET_PASSWORD` |

**`WALLET_DIR` differs by run target:**
- **Docker:** `/app/wallet` (compose mounts `./wallet` there read-only). This is the `.env` value.
- **Local (uvicorn / pytest helper):** set the env var to the absolute local `wallet/` path —
  e.g. `$env:WALLET_DIR = "<repo>\wallet"` — which overrides the `.env` value (env > .env in
  pydantic-settings).

**Verify connectivity before building features:** `GET /health` runs `SELECT 1 FROM dual` and
returns `{status, database, error}`. A green `/health` means the wallet + thin-mode config is
correct — that is the single biggest infra risk for this project.

## Secrets — never commit

`.gitignore` excludes `wallet/`, `.env`, `.env.*` (except `.env.example`), and key material
(`*.sso`, `*.pem`, `*.p12`, `*.jks`). Before any commit that touches config, confirm with
`git status --ignored` that `wallet/` and `.env` are listed as ignored.

- Real secrets live only in `.env` (local) / container secrets (deploy) — never in code, never in
  `.env.example` (placeholders like `__FILL_ME__` only).
- The wallet password cannot be recovered. If lost, re-download the wallet from the OCI console
  with a new password and overwrite `wallet/`; the DSN is unchanged so `.env` needs no edit.

## Database migrations (Alembic)

- **Never modify an already-applied migration.** Add a new one.
- Generate: `alembic revision --autogenerate -m "describe change"`; apply: `alembic upgrade head`.
- The engine/URL comes from `app.core.config` via `alembic/env.py` — there is intentionally no URL
  in `alembic.ini` (it would leak wallet details into source control).
- **`env.py` has an `include_name` filter** that restricts autogenerate to tables defined in our
  models. ADB ships Oracle-managed tables (e.g. `dbtools$execution_history` from Database Actions);
  without the filter, autogenerate emits a destructive `drop_table` against Oracle's own objects.
  Always review generated migrations and confirm no system table is dropped.
- Integer PK columns must render with `sa.Identity(always=False)` in the migration (matches the
  `Identity()` on the model). Check this on every new table.

## Testing

- **Framework:** `pytest`. Assertions are plain `assert` (no extra assertion lib).
- **Pure logic** (auth, balance, validation) runs against **SQLite in-memory** — fast, no Oracle,
  no `oracledb` needed. `tests/conftest.py` builds the engine and overrides `get_session`.
- **Oracle-specific behaviour** (sequences, `Identity`, Oracle Text, `FOR UPDATE`) is verified
  against ADB directly (or Oracle XE in CI later) — SQLite cannot prove it.
- **Required** for any DB-mutating operation and money logic.
- Run: `pytest`.

> SQLite hides Oracle constraints. A green SQLite suite is necessary but not sufficient — for
> schema/identity/locking changes, also exercise the path against ADB.

## Coding conventions

- **PEP 8** + standard Python naming (`snake_case` functions/vars, `PascalCase` classes).
- **Full type hints** on function signatures; `mypy` runs in `strict` mode — keep it green.
- `ruff` handles lint + import ordering; keep it clean before committing.
- **Pydantic v2** for every request/response model — never accept/return raw dicts at the boundary.
- Prefer explicit over clever; keep functions short and single-purpose.
- Comments only when the *why* is non-obvious (the *what* should be readable from the code).

### Language — English only

All source code is **English** — comments, names, string literals, config annotations,
`.env.example` comments, commit messages. UI-facing strings shown to users (Flutter app) may be
Vietnamese/bilingual; this rule is about the codebase, not product copy.

### No personal information / secrets in code

Never hardcode PII (names-as-data, phone numbers, emails) or secrets in source. Config comes from
environment variables; data lives in the database. If secrets are ever committed by accident,
rewrite history (`git filter-repo --replace-text`) and force-push — don't leave them reachable.

## Git workflow

- Default branch: `master`. History from the previous project (`htford`) is intentionally kept.
- Branch for real work: `feature/short-description` or `bug/short-description` off `master`.
- Open a PR into `master`; merge with a **merge commit** (no squash/rebase).
- Commit messages: short imperative subject, bullet body for meaningful changes; skip trivial noise.
- There is no auto-deploy pipeline yet — direct pushes during early scaffolding are acceptable, but
  prefer PRs once the app is in real use.

### Author identity & co-authorship

This is a **personal** repo — commits must use the personal identity, never the cisbox company
email (the machine's global git config defaults to the company email, so set it locally per clone):

```bash
git config --local user.name "vodongha"
git config --local user.email "vodongha@hotmail.com"
```

Commits made with AI assistance end with a co-author trailer (matching the `vodongha-personal`
convention), using the actual model:

```
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

## Gotchas (learned the hard way — read before debugging these)

- **PyPI package is `oracledb`, not `python-oracledb`.** Installing `python-oracledb` fails with
  "from versions: none". The import is `import oracledb`; the product name in docs is
  "python-oracledb". `pyproject.toml` depends on `oracledb`.
- **Don't use `passlib`.** `passlib` 1.7.4 is unmaintained and breaks against `bcrypt` 5.x
  (missing `__about__`, spurious "password cannot be longer than 72 bytes"). Use the `bcrypt`
  library directly (`bcrypt.hashpw` / `bcrypt.checkpw`). Note bcrypt only hashes the first 72 bytes.
- **Oracle PK needs explicit `Identity()`.** SQLite auto-increments an integer PK silently, so the
  test suite passes; Oracle raises `ORA-01400: cannot insert NULL into ...ID`. Declare
  `mapped_column(Identity(), primary_key=True)` and render `sa.Identity(always=False)` in migrations.
- **Alembic autogenerate wants to drop Oracle system tables** (`dbtools$execution_history`). The
  `include_name` filter in `alembic/env.py` prevents this — keep it, and review every autogen diff.
- **`WALLET_DIR` is `/app/wallet` in `.env` (Docker).** For local runs, override the env var to the
  absolute local wallet path; env vars beat `.env` in pydantic-settings.
- **Thin mode uses `ewallet.pem` + wallet password**, not `cwallet.sso`. A missing/blank
  `WALLET_PASSWORD` means no connection.

## Roadmap

Vertical-slice-first. Target: a family using it for real around week ~4; full v1 ~14 weeks.

| Phase | Content |
|---|---|
| 0 | Landing page validation |
| 1 ✅ | Connection spike + JWT auth + User/Family (this scaffold) → next: one wallet + expense/income + dashboard total |
| 2 | Multi-member: invitations, roles, `family_id` scope hardening + tests |
| 3 | Categories + multiple wallets + transfer (with locking) |
| 4 | Reports: by member / category / month |
| 5 | Budgets + alerts (Celery Beat) |
| 6 | Recurring transactions (Celery Beat) |
| 7 | Receipt upload (MinIO) + OCR (pytesseract) |
| 8 | Auto-categorize: merchant dictionary first, Ollama for misses |
| 9 | Hardening: money/scope test coverage, ADB backup, monitoring, store submission |
