# Family Budget — CLAUDE.md

## Project overview

Multi-member household expense tracker. A family shares wallets and records income/expense
together; every member sees the same data, scoped to their family. Multi-tenant by `family_id`.

- **Repo:** https://github.com/vodongha/family-budget (private; renamed from `htford`, git history preserved)
- **Backend:** FastAPI (Python) REST API
- **Mobile:** Flutter (Android + iOS) — separate workspace / `mobile/` later
- **Host (planned):** Oracle Cloud Ampere A1 free tier, all containers
- **Domain:** `famo.io.vn` (production API). The privacy-policy URL for Google Play is
  `https://famo.io.vn/privacy`; the app builds with `--dart-define=API_BASE_URL=https://famo.io.vn`.
- **Status:** Phase 1 — connection spike + auth skeleton landed and verified against live ADB.

The architecture deliberately mirrors a layered service design (the author's day-job pattern):
**router → service → repository**. Keep that separation; it is the backbone of the project.

- **Wiki:** https://github.com/vodongha/family-budget/wiki (Architecture, Connection & Wallet,
  Database & Migrations, API Reference, Testing, Git Workflow). Update the relevant wiki page when
  behaviour it documents changes.
- **CI:** `.github/workflows/ci.yml` runs `ruff check` + `pytest` (SQLite, no ADB) on pushes/PRs to
  `master`. Keep it green.

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
- **Transfers** are two linked transaction legs (`transfer_out` from source, `transfer_in` to
  destination) sharing a `transfer_group_rid`. An **internal** transfer (both legs inside the scope
  being viewed) is **excluded** from income/expense totals and statistics — it just moves money.
  But a transfer that **crosses the scope boundary** (e.g. personal→family: one leg in a wallet
  outside the current scope) *is* real income (`transfer_in`) or expense (`transfer_out`) for that
  scope, so dashboard/stats count it (`TransactionRepository.boundary_transfer_legs`). This keeps a
  scope's `net = income − expense` consistent with its wallet balances. Don't count internal
  transfers as income/expense.
- If you touch balance computation, transaction writes, or the `family_id` scope, **write a test**
  before you change behaviour. A wrong write at family scale is worse than a slow feature.
- **Multi-currency.** Each wallet has an ISO-4217 `currency` (default `VND`); its amounts/balance
  are minor units of **that** currency (`app/core/currency.py` holds the supported set + decimals).
  Per-wallet figures display in the wallet's own currency; any total that spans wallets (dashboard
  income/expense/net, stats, budget `spent`) is converted to the **base currency (VND)** via
  `CurrencyConverter` (`app/domains/rates/`), which reads the `exchange_rates` table (refreshed by a
  Celery-beat job from open.er-api.com, seeded by migration). **Never sum raw minor units across
  currencies.** Transfers require both wallets to share a currency (cross-currency is rejected).
  **Display currency.** Cross-wallet totals (dashboard/stats/budget) accept an optional
  `display_currency` query param (the `DisplayCurrency` dep in `app/core/deps.py`, 422 on an
  unsupported code) and are converted base→that currency via `CurrencyConverter.base_to_target`
  (`convert_from_base` in `app/core/currency.py`). Per-wallet balances always stay in their own
  currency. Budgets store the limit in the **base** currency; the `amount` in/out of the budget
  endpoints is in the request's display currency (converted on save/read), so it follows the
  client's chosen currency without a schema change. `GET /rates` reports rate freshness
  (`{base_currency, updated_at, count}`) and `POST /rates/refresh` runs the fetch on demand (`503`
  if the source is unreachable) — the same fetch the 12h Celery-beat job runs.

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

### Domains

Built: `users`, `auth`, `families`, `invitations`, `categories`, `wallets`, `transactions`,
`transfers`, `budgets`, `dashboard`, `stats`, `account`, `legal`, `health`. Planned: `reports`,
`ocr`, `ai`. Each follows the same `router / service / repository / schemas / models (/ tasks for
Celery)` layout (`legal` is router-only — it serves a static HTML page, no DB).

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

### Tenant scope — `get_current_family` / `get_optional_family`

`app/core/deps.py` exposes `CurrentFamily` (an `int family_id`, **403** if the user has none) and
`OptionalFamily` (`int | None`). Family-only features (budgets, categories, members, invitations,
transfer-ownership) use `CurrentFamily`. Features that also serve the **personal** space — wallets,
transactions, transfers, dashboard, stats — use `OptionalFamily`, because **personal data works
without a family**.

**Personal vs family scoping (important).** `wallets.family_id` and `transactions.family_id` are
**nullable**. A **personal** wallet is owned by `owner_user_id`, has `family_id = null`, and is
visible regardless of family; a **family** wallet has `family_id` set + `visibility = family`.
`visibility_clause(family_id, user_id, scope)` encodes this (personal = owner-only, family = the
family's shared wallets, empty when `family_id is None`). Transaction/balance/stats queries scope by
**`wallet_id ∈ visible_wallet_ids`** (which already encodes permission) — they do **not** filter by
`family_id`, so they work for personal wallets too. A transaction's `family_id` just mirrors its
wallet's. Don't re-add a `Transaction.family_id == family_id` filter.

### Account deletion & data retention (Google Play policy)

Self-service deletion is **soft-delete + scheduled purge**, so the in-app and data-deletion
requirements are both met:

- `DELETE /auth/me` sets `users.is_deleted` + `deleted_at`. Login and `get_current_user`
  reject deleted users immediately (401), even with an otherwise-valid token.
- **Owner rule:** an owner with other active members is blocked (`409`) — ownership must move
  first (`POST /families/transfer-ownership {target_rid}`, owner-only, single-owner: the old
  owner becomes a member), so a family is never orphaned. A **sole** owner also soft-deletes
  the family.
- **Purge job** (`app/domains/account/maintenance.py`, Celery Beat, daily): once `deleted_at`
  is older than `RETENTION_DAYS` (30), a fully-deleted **family** is hard-purged with all its
  data (transactions → wallets → invitations → members → family); a **member** soft-deleted
  inside a still-active family is **anonymised** (PII scrubbed) rather than deleted, because
  `transactions.created_by_user_id` is `NOT NULL` and references their row. The
  anonymised member's **personal** wallets (and their transactions) are purged
  too — private data no one else can see; shared family data stays.
- `PATCH /auth/me` updates the display name and optional **phone** (E.164, validated with
  `phonenumbers` in `app/core/phone.py`, unique; blank clears it).

### Family membership (`app/domains/families/`)

`GET /members` lists active members; `POST /families/transfer-ownership` hands ownership to
another active member (owner-only, single-owner). Management:
- `PATCH /families {name}` — rename (owner-only).
- `DELETE /families` — delete the family + its **shared** data (`FamilyRepository.purge_family`),
  owner-only and **only when no other members remain** (`409` otherwise). Personal data is kept; the
  owner is detached. Returns a fresh JWT (family-less).
- `POST /families/leave` — a member leaves (personal data kept); an owner with other members must
  transfer first (`409`); a sole member leaving tears the empty family down. Fresh JWT.
- `DELETE /families/members/{rid}` — owner removes a member (their personal data stays; `400` on
  self, `404` if not a member).

Anything that changes the caller's own `family_id` (create/delete/leave) returns a **fresh JWT**
(the token embeds `family_id`); the app stores it and refreshes.

### Invitations to existing accounts

**Any active family member can invite** (not just the owner); the invitee always joins with the
`member` role (a non-owner inviter can't grant a higher role). `POST /invitations` matches the
email/phone to an existing account (`invitations.target_user_id`).
A match becomes an **in-app invite** (no registration link): the invitee reads `GET /invitations/inbox`
and accepts via `POST /invitations/{rid}/accept-existing`, which moves them into the family
(their now-empty old family is soft-deleted; an owner with other members gets `409` — transfer
first) and returns a fresh JWT. `decline` dismisses it. New (unmatched) contacts keep the public
link + register flow.

### CORS

`app/main.py` adds `CORSMiddleware`. The Flutter **web** client runs on a different origin and
calls this API from the browser; auth is a Bearer token (no cookies), so `allow_origins=["*"]`
is acceptable. Tighten to specific origins for production.

### Sign in with Google

`POST /auth/google` accepts a Google **ID token** from the client and verifies it with
`google-auth` (`app/core/google.py`, isolated so tests can mock it). The token's audience
must be one of `settings.google_client_id` (comma-separated to allow web + Android + iOS
client IDs). It then links the Google `sub` to an existing user with the same email
(**matched case-insensitively** via `func.lower` — Google returns a lowercased email, so the
same person stays one account), or creates a brand-new account with **no family** (it
creates/joins one after first sign-in, like password registration). Google-only accounts have
an **empty password hash** and can't password-login (until they set one via
`POST /auth/change-password`); deleting an account clears `google_sub` (unlink). Set
`GOOGLE_CLIENT_ID` in the environment to enable it.

### Accounts, families & passwords

Registration creates an **account**, not necessarily a family: `RegisterRequest.family_name`
is **optional**. Omitted → the account has no family yet (`users.family_id` is nullable;
`UserRead.has_family` is false) and the client routes it to onboarding to **create or join**
one. Supplied → a family is created and the registrant owns it (back-compat / one-step path).
`POST /families` creates a family for the signed-in family-less account, makes it the owner,
seeds default categories, and returns a **fresh JWT** carrying the new family scope (`409` if
it already has a family). `POST /auth/change-password` changes the password (`current_password`
required) — or sets the first password for a Google-only account (omit `current_password`);
`UserRead.has_password` tells the client which. Emails are stored lowercased and looked up
case-insensitively (`AuthRepository.get_user_by_email`).

### Wallet privacy (personal vs family)

A wallet is either **family** (shared — every member sees it, its transactions,
balance, and totals) or **personal** (private — only its `owner_user_id` can see
it). `wallets.visibility` + `wallets.owner_user_id` carry this. The rule lives in
`WalletRepository.visibility_clause` and **every** wallet read goes through it, so
a member can never see (or write into) another member's personal wallet — not even
the family owner. `get_visible_by_rid` returns `None` for a wallet the caller may
not see (404, no existence leak).

Reads accept a `scope` query param (`WalletScope`): `all` (default — family +
caller's own personal), `family`, or `personal`. It threads through
`GET /wallets`, `GET /dashboard/summary`, `GET /transactions`, and both `/stats`
endpoints — each constrains its transaction/balance aggregation to the caller's
visible wallet ids. **Delete:** a personal wallet by its owner; a shared family
wallet by the family owner **or the member who created it** (`403` otherwise).
New wallets default to family; `POST /wallets {visibility: "personal"}` makes a
private one (owner = creator). Each wallet records `created_by_user_id` (set on
create; the API returns `created_by_me` so the client can show edit/delete to the
creator); wallets created before this column have an unknown creator and stay
owner-managed. Each wallet also carries an optional **`icon`** (emoji) and
**`color`** (hex). `PATCH /wallets/{rid}` edits name/icon/color with the **same
permission as delete** (family wallet → family owner or creator, personal wallet →
its owner); visibility is immutable.

### Privacy policy (`app/domains/legal/`)

`GET /privacy?lang=vi|en` serves a **public, no-auth** bilingual HTML page (default `vi`). It is
the single source of truth for the policy: Google Play uses the URL for the store listing / Data
Safety form, and the Flutter app embeds the same URL in an in-app WebView. The router is the only
layer (`legal` has no service/repository) — content + inline CSS live in `router.py` as
per-language section bundles. Keep it framable (don't add `X-Frame-Options`) so the in-app WebView
and the web iframe can load it. Update `EFFECTIVE_DATE` when the policy text changes.

### Statistics

`GET /stats/monthly?months=N` (`app/domains/stats/`) returns per-month income/expense totals.
`GET /stats/calendar?year=&month=` returns per-day income/expense for one month (the calendar
screen's net markers + day summary), only for days with activity. All stats endpoints take an
optional `display_currency` and convert their totals to it.
`GET /stats/by-category?kind=expense|income&months=N` returns per-category totals for one kind,
sorted by amount descending; uncategorized transactions fold into one bucket (`category_rid`
null, `default_key` `"uncategorized"`). Aggregation is done **in Python** (not a SQL `GROUP BY`
with date functions) so the query stays portable across Oracle and the SQLite test database.

### Transactions: edit / delete / filter

Beyond create + list, `PATCH /transactions/{rid}` (full update) and `DELETE /transactions/{rid}`
operate only on transactions whose wallet is visible to the caller (same privacy guard). `GET
/transactions` accepts `type`, `category_rid`, `date_from`, `date_to` filters on top of
`wallet_rid`/`scope`/`limit`.

### Budgets (`app/domains/budgets/`)

A budget is a **monthly spending limit per category**, family-level (one per category, unique
`(family_id, category_id)`). `GET /budgets` returns each budget with its current-month `spent`
(summed over **family** wallets so personal spending stays private), derived — never stored.
`POST` (`409` on duplicate), `PATCH {amount}`, `DELETE`.

### Transfers (`app/domains/transfers/`)

`POST /transfers {from_wallet_rid, to_wallet_rid, amount, ...}` creates the two linked legs (both
wallets must be visible to the caller; same wallet → `400`). `DELETE /transfers/{group_rid}`
removes both. See the money-rules note on why transfers stay out of income/expense totals.

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

**Dedicated schema (sharing one ADB across apps).** Set `ORACLE_SCHEMA` to put this app's tables in
a named schema instead of the connecting user's default — every connection then runs
`ALTER SESSION SET CURRENT_SCHEMA` (see `app/core/database.py`). The schema must exist first as an
Oracle user with quota; `scripts/create_schema.sql` creates a **schema-only** (`NO AUTHENTICATION`)
owner named `FAMILY_BUDGET` so there's no extra password, and the app keeps connecting as `ADMIN`.
Empty `ORACLE_SCHEMA` keeps the old behaviour (tables in the connecting user's schema).

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

AI-assisted commits are **authored by `vodongha`** with **Claude as the committer**:

```bash
GIT_COMMITTER_NAME="Claude Opus 4.8" GIT_COMMITTER_EMAIL="noreply@anthropic.com" \
  git commit --author="vodongha <vodongha@hotmail.com>" -m "..."
```

## Deployment (Fly.io)

Production runs on **Fly.io**, region `sin` (Singapore — closest to ADB), domain `famo.io.vn`.

- **CI/CD:** `.github/workflows/deploy.yml` deploys on push to `master` (ruff + pytest →
  `flyctl deploy --remote-only`, needs the `FLY_API_TOKEN` repo secret). `ci.yml` runs the same
  checks on PRs only (no double run on push). Mirrors the `vodongha-personal` website setup.
- **`fly.toml`:** two process groups from one image — `app` (FastAPI, the only HTTP group;
  `auto_stop = suspend`, `min_machines_running = 0`) and `worker` (`celery worker --beat`, runs
  continuously so the daily purge fires). `[deploy] release_command = "alembic upgrade head"`
  migrates before each release. VM 512MB each.
- **Wallet on Fly:** never committed/baked. `scripts/fly_entrypoint.sh` decodes base64 secrets
  (`WALLET_EWALLET_PEM_B64`, `WALLET_TNSNAMES_B64`, `WALLET_SQLNET_B64`) into `WALLET_DIR` at
  startup; the entrypoint runs for **every** process group so all machines get the wallet. Skipped
  when those vars are unset (local / docker-compose, where the wallet is bind-mounted).
- **Web client (same-origin):** the Dockerfile's first stage builds the Flutter **web** target
  from the public `family-budget-app` repo (`flutter create . --platforms=web` → `flutter build
  web` with `API_BASE_URL=https://famo.io.vn`) and copies it to `/app/web`. `main.py` mounts it
  with `StaticFiles(html=True)` at `/` **after** all API routers (the SPA uses hash routing, so no
  catch-all is needed). So `famo.io.vn` serves the app at `/` and the API at its routes — one
  origin, no CORS needed for the browser. The service-info JSON moved from `/` to `/meta`. The
  mount is guarded by directory existence, so local dev / tests (no `web/`) are unaffected.
- **Redis:** external (Celery broker). Provision Upstash via `fly redis create` and set
  `REDIS_URL`. The API itself never touches Redis — only the worker does.
- **Secrets** (set with `fly secrets set`, never committed): `ORACLE_PASSWORD`, `WALLET_PASSWORD`,
  `JWT_SECRET`, `GOOGLE_CLIENT_ID`, `REDIS_URL`, and the three `WALLET_*_B64`. See the README
  "Deploy (Fly.io)" section for the exact one-time commands.

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
- **Oracle enforces VARCHAR2 length; SQLite doesn't.** A value longer than the column width raises
  `ORA-12899` at runtime while the SQLite test suite passes. Size `String(n)` for the **longest**
  value a column can hold (e.g. `transactions.type` must fit `"transfer_out"` = 12 chars).
- **Oracle stores `''` as NULL.** Inserting an empty string into a `NOT NULL` column raises
  `ORA-01400` (SQLite accepts `''`, hiding it). For "optional text with a real absence" (e.g.
  `users.hashed_password` for Google-only accounts) make the column **nullable** and write `None`,
  never `""`.
- **Oracle has no native boolean — filter with `== true()`/`== false()`, never `.is_(True/False)`.**
  A `Boolean` column maps to `NUMBER(1)`; `.is_(False)` renders `... IS 0`, which Oracle rejects
  with `ORA-00908: missing NULL keyword` (`IS` is only valid with `NULL`). SQLite accepts `IS 0`,
  so the test suite passes while Oracle fails at runtime. Import `true, false` from `sqlalchemy`
  and compare with `==` (renders `= 1` / `= 0`).

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
