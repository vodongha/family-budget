"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.domains.auth.router import router as auth_router
from app.domains.budgets.router import router as budgets_router
from app.domains.categories.router import router as categories_router
from app.domains.dashboard.router import router as dashboard_router
from app.domains.families.router import router as families_router
from app.domains.health.router import router as health_router
from app.domains.invitations.router import router as invitations_router
from app.domains.legal.router import router as legal_router
from app.domains.stats.router import router as stats_router
from app.domains.transactions.router import router as transactions_router
from app.domains.transfers.router import router as transfers_router
from app.domains.wallets.router import router as wallets_router

# Long-form description rendered on the Swagger / ReDoc landing page. Markdown is
# supported, so this reads like a short guide rather than a bare title.
DESCRIPTION = """
The REST API behind **Family Budget** — a multi-member household expense tracker.
A *family* shares wallets and records income and expense together; every member
sees the same data, always scoped to their own family.

### How to use these docs

1. **Register** a family with `POST /auth/register` (you become its **owner**), or
   **sign in** with `POST /auth/login` (or `POST /auth/google`).
2. Click **Authorize** (top right) and paste the `access_token` you got back. Every
   protected endpoint then sends it as a `Bearer` token for you.
3. Explore the grouped sections below — each tag is one domain of the app.

### Conventions used everywhere

- **Money is integer đồng** (`int`), never a decimal. The amount you send is always
  positive; *direction* comes from the transaction **type** (`expense` / `income`),
  not the sign. Wallet balances are **derived** on the server, never sent by clients.
- **Public IDs are `rid`s** — a 26-char ULID. Internal numeric ids are never exposed.
- **Tenant scope** — every family-owned resource is filtered by your family. You can
  never read or write another family's data, and personal wallets stay private even
  from the family owner.

### Common error responses

| Status | Meaning |
|---|---|
| `401` | Missing, expired, or invalid token (sign in again). |
| `403` | Authenticated, but not allowed (e.g. an owner-only action). |
| `404` | Not found *in your family* (cross-family access looks identical to absent). |
| `409` | Conflict — a duplicate, or a rule that must be resolved first. |
| `422` | Validation failed on the request body or query. |
"""

# Tag metadata controls the order and the explanatory blurb of each grouped section
# in the docs. Order here is the order shown in Swagger UI.
TAGS_METADATA = [
    {
        "name": "meta",
        "description": "Service metadata — the API root and environment.",
    },
    {
        "name": "health",
        "description": "Liveness / readiness probe. `GET /health` runs "
        "`SELECT 1` against the database and reports connectivity.",
    },
    {
        "name": "auth",
        "description": "Register, sign in (password or Google), read and update your "
        "profile, and self-service account deletion.",
    },
    {
        "name": "family",
        "description": "The family roster and ownership. List members and transfer "
        "ownership to another member (owner-only, single-owner model).",
    },
    {
        "name": "invitations",
        "description": "Bring people into a family. Existing accounts get an in-app "
        "invite (inbox → accept/decline); new contacts get a shareable registration link.",
    },
    {
        "name": "categories",
        "description": "Family-scoped income / expense categories (emoji + colour) "
        "used to tag transactions.",
    },
    {
        "name": "wallets",
        "description": "Shared (family) or personal (private) wallets. Balances are "
        "derived from transactions; a `scope` selects which wallets a read covers.",
    },
    {
        "name": "transactions",
        "description": "Create, edit, delete and list income / expense entries. "
        "Supports filtering by type, category and date range.",
    },
    {
        "name": "transfers",
        "description": "Move money between two wallets as two linked legs. Transfers "
        "affect balances but are excluded from income / expense totals and statistics.",
    },
    {
        "name": "budgets",
        "description": "Per-category monthly spending limits with the current month's "
        "derived spend.",
    },
    {
        "name": "dashboard",
        "description": "The home summary — net balance, totals, and per-wallet balances "
        "for a chosen scope.",
    },
    {
        "name": "stats",
        "description": "Aggregations for charts — monthly income / expense series and "
        "per-category breakdowns.",
    },
    {
        "name": "legal",
        "description": "Public legal pages. `GET /privacy` serves the bilingual "
        "(vi/en) privacy policy used for the Google Play listing.",
    },
]

app = FastAPI(
    title="Family Budget API",
    version="1.0.0",
    summary="Multi-member household expense tracker — REST API.",
    description=DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    contact={"name": "Võ Đông Hà", "url": "https://vodongha.id.vn"},
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    # Swagger UI tweaks: collapse the operation list by default, sort tags and
    # operations alphabetically, and keep the entered token across page reloads.
    swagger_ui_parameters={
        "docExpansion": "none",
        "tagsSorter": "alpha",
        "operationsSorter": "method",
        "persistAuthorization": True,
        "displayRequestDuration": True,
    },
)

# CORS — the Flutter web client runs on a different origin and calls this API
# from the browser. Auth uses a Bearer token (no cookies). Origins are
# configurable via CORS_ORIGINS (comma-separated); defaults to "*" until a fixed
# web domain exists. Native mobile apps don't send an Origin header, so this only
# affects the browser client.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(legal_router)
app.include_router(auth_router)
app.include_router(families_router)
app.include_router(invitations_router)
app.include_router(categories_router)
app.include_router(budgets_router)
app.include_router(wallets_router)
app.include_router(transactions_router)
app.include_router(transfers_router)
app.include_router(dashboard_router)
app.include_router(stats_router)


@app.get(
    "/",
    tags=["meta"],
    summary="Service root",
    description="Returns the app name and the running environment.",
)
def root() -> dict[str, str]:
    return {"app": "family-budget", "env": settings.env}
