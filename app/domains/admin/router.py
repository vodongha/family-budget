"""Admin panel routes — server-rendered (Jinja2), session-authenticated.

Mounted under ``/admin``. Registered before the SPA static mount in
``app.main`` so these paths win over the Flutter web app served at ``/``.
"""

import hashlib
from datetime import date
from pathlib import Path
from typing import Annotated, Any

import sass
from fastapi import APIRouter, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_303_SEE_OTHER

from app.core.config import settings
from app.core.deps import SessionDep
from app.domains.admin.deps_panel import dependency_report, library_report
from app.domains.admin.money import to_major, to_minor
from app.domains.admin.pagination import is_partial, table_params
from app.domains.admin.repository import (
    AUDIT_SORTS,
    FAMILIES_SORTS,
    TRANSACTIONS_SORTS,
    USERS_SORTS,
)
from app.domains.admin.security import (
    LOGIN_PATH,
    AdminCsrfError,
    AdminLoginRequired,
    CurrentAdmin,
    csrf_token,
    flash,
    login_admin,
    logout_admin,
    pop_flashes,
    verify_csrf,
)
from app.domains.admin.service import AdminService
from app.domains.categories.models import CategoryKind
from app.domains.transactions.models import TransactionType
from app.domains.users.models import User, UserRole

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.filters["money"] = to_major

# SCSS source + the directory the compiled stylesheet is served from.
_STYLES_DIR = Path(__file__).resolve().parent / "styles"
_STATIC_DIR = Path(__file__).resolve().parent / "static"


def _build_admin_css() -> str:
    """Compile ``styles/admin.scss`` → ``static/admin.css`` and return a short
    content hash used to cache-bust the ``<link>`` in base.html.

    Run once at startup (see :func:`setup_admin`). The compiled CSS is a build
    artifact — it's git-ignored and regenerated on every boot, so the SCSS
    partials stay the single source of truth.
    """
    css = sass.compile(filename=str(_STYLES_DIR / "admin.scss"), output_style="compressed")
    _STATIC_DIR.mkdir(exist_ok=True)
    (_STATIC_DIR / "admin.css").write_text(css, encoding="utf-8")
    return hashlib.sha256(css.encode("utf-8")).hexdigest()[:8]


router = APIRouter(prefix="/admin", tags=["admin"], include_in_schema=False)

_REDIRECT = HTTP_303_SEE_OTHER


def _ctx(
    request: Request,
    admin: User,
    active: str,
    crumbs: list[dict[str, str]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "admin": admin,
        "csrf": csrf_token(request),
        "flashes": pop_flashes(request),
        "active": active,
        "crumbs": crumbs or [],
        **extra,
    }


# Column headers per server-side table. A blank ``key`` is a non-sortable
# column (joined/derived values the query can't ORDER BY cheaply); a key must
# match the table's *_SORTS map in the repository.
_USERS_COLUMNS = [
    {"key": "email", "label": "Email"},
    {"key": "display_name", "label": "Name"},
    {"key": "phone", "label": "Phone"},
    {"key": "role", "label": "Role"},
    {"key": "is_superadmin", "label": "Admin"},
    {"key": "", "label": "Family"},
    {"key": "is_deleted", "label": "Status"},
    {"key": "created_at", "label": "Created"},
]
_FAMILIES_COLUMNS = [
    {"key": "name", "label": "Name"},
    {"key": "", "label": "Members"},
    {"key": "", "label": "Wallets"},
    {"key": "is_deleted", "label": "Status"},
    {"key": "created_at", "label": "Created"},
]
_AUDIT_COLUMNS = [
    {"key": "created_at", "label": "When"},
    {"key": "action", "label": "Action"},
    {"key": "", "label": "Target"},
    {"key": "", "label": "Detail"},
]
_TRANSACTIONS_COLUMNS = [
    {"key": "occurred_on", "label": "Date"},
    {"key": "", "label": "Wallet"},
    {"key": "type", "label": "Type"},
    {"key": "amount", "label": "Amount"},
    {"key": "", "label": "Category"},
    {"key": "", "label": "By"},
    {"key": "", "label": ""},
]
_WALLET_TXN_COLUMNS = [
    {"key": "occurred_on", "label": "Date"},
    {"key": "type", "label": "Type"},
    {"key": "amount", "label": "Amount"},
    {"key": "", "label": "Category"},
    {"key": "", "label": "Note"},
    {"key": "", "label": "By"},
    {"key": "", "label": ""},
]
_USER_WALLET_COLUMNS = [
    {"key": "name", "label": "Name"},
    {"key": "currency", "label": "Currency"},
    {"key": "visibility", "label": "Visibility"},
    {"key": "balance", "label": "Balance"},
    {"key": "", "label": ""},
]
_USER_TXN_COLUMNS = [
    {"key": "occurred_on", "label": "Date"},
    {"key": "", "label": "Wallet"},
    {"key": "type", "label": "Type"},
    {"key": "amount", "label": "Amount"},
    {"key": "", "label": "Note"},
]
_FAMILY_MEMBER_COLUMNS = [
    {"key": "display_name", "label": "Name"},
    {"key": "email", "label": "Email"},
    {"key": "role", "label": "Role"},
    {"key": "", "label": ""},
]
_FAMILY_WALLET_COLUMNS = [
    {"key": "name", "label": "Name"},
    {"key": "currency", "label": "Currency"},
    {"key": "balance", "label": "Balance"},
    {"key": "", "label": ""},
]
_FAMILY_CATEGORY_COLUMNS = [
    {"key": "name", "label": "Name"},
    {"key": "kind", "label": "Kind"},
    {"key": "", "label": "Icon"},
    {"key": "", "label": "Color"},
    {"key": "", "label": ""},
]
_FAMILY_BUDGET_COLUMNS = [
    {"key": "category", "label": "Category"},
    {"key": "amount", "label": "Limit (VND)"},
    {"key": "", "label": ""},
]
_DEPS_COLUMNS = [
    {"key": "package", "label": "Package"},
    {"key": "ecosystem", "label": "Ecosystem"},
    {"key": "severity", "label": "Severity"},
    {"key": "", "label": "Vulnerable"},
    {"key": "", "label": "Patched"},
    {"key": "created_at", "label": "Opened"},
    {"key": "", "label": ""},
]


def _sort_keys(columns: list[dict[str, str]]) -> dict[str, str]:
    """The sortable keys of a column set — passed to ``table_params`` to validate
    the ``sort`` query param for the in-memory (derived) tables."""
    return {c["key"]: c["key"] for c in columns if c["key"]}


def _fragment(
    request: Request,
    *,
    rows_template: str,
    columns: list[dict[str, str]],
    page: Any,
    **extra: Any,
) -> HTMLResponse:
    """Render just the rows+footer fragment for one server-side table (used by
    detail pages that host several tables, dispatched by a ``?table=`` param)."""
    return templates.TemplateResponse(
        request,
        "_table_fragment.html",
        {
            "rows_template": rows_template,
            "columns": columns,
            "page": page,
            "csrf": csrf_token(request),
            **extra,
        },
    )


def _table(
    request: Request,
    admin: User,
    *,
    active: str,
    crumbs: list[dict[str, str]],
    page_template: str,
    rows_template: str,
    table_id: str,
    endpoint: str,
    columns: list[dict[str, str]],
    page: Any,
    **extra: Any,
) -> HTMLResponse:
    """Render a server-side table: the full page on a normal request, or just
    the rows+footer fragment when the datatable JS asks for one (``?partial=1``).
    """
    data: dict[str, Any] = {
        "table_id": table_id,
        "endpoint": endpoint,
        "columns": columns,
        "rows_template": rows_template,
        "page": page,
        # Rows may carry per-row POST forms (e.g. delete), so the CSRF token has
        # to travel with the fragment too, not just the full page.
        "csrf": csrf_token(request),
        **extra,
    }
    if is_partial(request):
        return templates.TemplateResponse(request, "_table_fragment.html", data)
    return templates.TemplateResponse(
        request,
        page_template,
        {**_ctx(request, admin, active, crumbs=crumbs, **extra), **data},
    )


def _check_csrf(request: Request, csrf: str) -> bool:
    try:
        verify_csrf(request, csrf)
        return True
    except AdminCsrfError:
        flash(request, "Session expired — please try again.", "error")
        return False


# --- auth ------------------------------------------------------------------


def _is_logged_in(request: Request, session: SessionDep) -> bool:
    rid = request.session.get("admin_rid")
    return bool(rid and AdminService(session).get_active_admin(rid))


@router.get("/login", response_class=HTMLResponse, response_model=None)
def login_form(request: Request, session: SessionDep) -> HTMLResponse | RedirectResponse:
    if _is_logged_in(request, session):
        return RedirectResponse("/admin", status_code=_REDIRECT)
    return templates.TemplateResponse(
        request, "login.html", {"csrf": csrf_token(request), "error": None}
    )


@router.post("/login", response_class=HTMLResponse, response_model=None)
def login_submit(
    request: Request,
    session: SessionDep,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    try:
        verify_csrf(request, csrf)
    except AdminCsrfError:
        return RedirectResponse(LOGIN_PATH, status_code=_REDIRECT)
    user = AdminService(session).authenticate(email, password)
    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"csrf": csrf_token(request), "error": "Invalid credentials"},
            status_code=401,
        )
    login_admin(request, user)
    return RedirectResponse("/admin", status_code=_REDIRECT)


@router.post("/logout")
def logout(request: Request, csrf: Annotated[str, Form()] = "") -> RedirectResponse:
    logout_admin(request)
    return RedirectResponse(LOGIN_PATH, status_code=_REDIRECT)


# --- dashboard + lists -----------------------------------------------------


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, session: SessionDep, admin: CurrentAdmin) -> HTMLResponse:
    svc = AdminService(session)
    data = svc.dashboard()
    # The "recent activity" widget is the audit table, backed by the /admin/audit
    # server-side endpoint (so sort/search/paging fetch from there).
    audit = svc.audit_page(
        table_params(request, allowed_sorts=AUDIT_SORTS, default_sort="created_at")
    )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        _ctx(
            request,
            admin,
            "dashboard",
            metrics=data["metrics"],
            rates_updated_at=data["rates_updated_at"],
            audit_page=audit,
            audit_columns=_AUDIT_COLUMNS,
        ),
    )


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, session: SessionDep, admin: CurrentAdmin) -> HTMLResponse:
    params = table_params(request, allowed_sorts=USERS_SORTS, default_sort="created_at")
    page = AdminService(session).users_page(params)
    return _table(
        request,
        admin,
        active="users",
        crumbs=[{"label": "Users"}],
        page_template="users.html",
        rows_template="_rows_users.html",
        table_id="tbl-users",
        endpoint="/admin/users",
        columns=_USERS_COLUMNS,
        page=page,
    )


@router.get("/families", response_class=HTMLResponse)
def families_page(
    request: Request, session: SessionDep, admin: CurrentAdmin
) -> HTMLResponse:
    params = table_params(request, allowed_sorts=FAMILIES_SORTS, default_sort="created_at")
    page = AdminService(session).families_page(params)
    return _table(
        request,
        admin,
        active="families",
        crumbs=[{"label": "Families"}],
        page_template="families.html",
        rows_template="_rows_families.html",
        table_id="tbl-families",
        endpoint="/admin/families",
        columns=_FAMILIES_COLUMNS,
        page=page,
    )


@router.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, session: SessionDep, admin: CurrentAdmin) -> HTMLResponse:
    params = table_params(request, allowed_sorts=AUDIT_SORTS, default_sort="created_at")
    page = AdminService(session).audit_page(params)
    return _table(
        request,
        admin,
        active="audit",
        crumbs=[{"label": "Audit log"}],
        page_template="audit.html",
        rows_template="_rows_audit.html",
        table_id="tbl-audit",
        endpoint="/admin/audit",
        columns=_AUDIT_COLUMNS,
        page=page,
    )


# --- create user -----------------------------------------------------------


@router.get("/users/new", response_class=HTMLResponse)
def user_new_form(
    request: Request, session: SessionDep, admin: CurrentAdmin
) -> HTMLResponse:
    svc = AdminService(session)
    return templates.TemplateResponse(
        request,
        "user_new.html",
        _ctx(
            request,
            admin,
            "users",
            crumbs=[{"label": "Users", "href": "/admin/users"}, {"label": "New user"}],
            roles=[r.value for r in UserRole],
            families=svc.active_families(),
        ),
    )


@router.post("/users")
def user_create(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    email: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    display_name: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    role: Annotated[str, Form()] = UserRole.MEMBER.value,
    is_superadmin: Annotated[bool, Form()] = False,
    family_rid: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    if not _check_csrf(request, csrf):
        return RedirectResponse("/admin/users/new", status_code=_REDIRECT)
    if not email.strip() or not display_name.strip() or len(password) < 8:
        flash(request, "Email, name, and a password (≥8 chars) are required.", "error")
        return RedirectResponse("/admin/users/new", status_code=_REDIRECT)
    family = svc.get_family(family_rid) if family_rid else None
    try:
        user = svc.create_user(
            email=email,
            password=password,
            display_name=display_name,
            phone=phone,
            role=role,
            is_superadmin=is_superadmin,
            family_id=family.id if family else None,
        )
    except Exception:  # noqa: BLE001 — surface duplicate email/phone to the admin
        session.rollback()
        flash(request, "Could not create (email or phone already in use?).", "error")
        return RedirectResponse("/admin/users/new", status_code=_REDIRECT)
    svc.log(admin, "user.create", target_type="user", target_rid=user.rid)
    flash(request, "User created.")
    return RedirectResponse(f"/admin/users/{user.rid}", status_code=_REDIRECT)


# --- user detail + actions -------------------------------------------------


@router.get("/users/{rid}", response_class=HTMLResponse, response_model=None)
def user_detail(
    request: Request, session: SessionDep, admin: CurrentAdmin, rid: str
) -> HTMLResponse | RedirectResponse:
    svc = AdminService(session)
    user = svc.get_user(rid)
    if user is None:
        flash(request, "User not found.", "error")
        return RedirectResponse("/admin/users", status_code=_REDIRECT)

    def wallets_page() -> Any:
        return svc.user_wallets_page(
            user,
            table_params(
                request,
                allowed_sorts=_sort_keys(_USER_WALLET_COLUMNS),
                default_sort="name",
            ),
        )

    def txns_page() -> Any:
        return svc.transactions_dt(
            table_params(
                request, allowed_sorts=TRANSACTIONS_SORTS, default_sort="occurred_on"
            ),
            created_by_user_id=user.id,
        )

    if is_partial(request):
        if request.query_params.get("table") == "txns":
            return _fragment(
                request,
                rows_template="_rows_user_txns.html",
                columns=_USER_TXN_COLUMNS,
                page=txns_page(),
            )
        return _fragment(
            request,
            rows_template="_rows_user_wallets.html",
            columns=_USER_WALLET_COLUMNS,
            page=wallets_page(),
        )

    return templates.TemplateResponse(
        request,
        "user_detail.html",
        _ctx(
            request,
            admin,
            "users",
            crumbs=[{"label": "Users", "href": "/admin/users"}, {"label": user.email}],
            user=user,
            wallets_page=wallets_page(),
            wallets_columns=_USER_WALLET_COLUMNS,
            txns_page=txns_page(),
            txns_columns=_USER_TXN_COLUMNS,
        ),
    )


@router.get("/users/{rid}/edit", response_class=HTMLResponse, response_model=None)
def user_edit_form(
    request: Request, session: SessionDep, admin: CurrentAdmin, rid: str
) -> HTMLResponse | RedirectResponse:
    user = AdminService(session).get_user(rid)
    if user is None:
        flash(request, "User not found.", "error")
        return RedirectResponse("/admin/users", status_code=_REDIRECT)
    return templates.TemplateResponse(
        request,
        "user_edit.html",
        _ctx(
            request,
            admin,
            "users",
            crumbs=[
                {"label": "Users", "href": "/admin/users"},
                {"label": user.email, "href": f"/admin/users/{user.rid}"},
                {"label": "Edit"},
            ],
            user=user,
            roles=[r.value for r in UserRole],
        ),
    )


@router.post("/users/{rid}/edit")
def user_edit_submit(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    display_name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    phone: Annotated[str, Form()] = "",
    role: Annotated[str, Form()] = UserRole.MEMBER.value,
    is_superadmin: Annotated[bool, Form()] = False,
) -> RedirectResponse:
    svc = AdminService(session)
    user = svc.get_user(rid)
    if user is None:
        flash(request, "User not found.", "error")
        return RedirectResponse("/admin/users", status_code=_REDIRECT)
    # Guard: an admin can't strip their own super-admin (avoid self-lockout).
    if user.id == admin.id and not is_superadmin:
        flash(request, "You can't remove your own admin access.", "error")
        return RedirectResponse(f"/admin/users/{rid}/edit", status_code=_REDIRECT)
    try:
        svc.update_user(
            user,
            display_name=display_name,
            email=email,
            phone=phone,
            role=role,
            is_superadmin=is_superadmin,
        )
    except Exception:  # noqa: BLE001 — surface duplicate email etc. to the admin
        session.rollback()
        flash(request, "Could not save (email already in use?).", "error")
        return RedirectResponse(f"/admin/users/{rid}/edit", status_code=_REDIRECT)
    svc.log(admin, "user.edit", target_type="user", target_rid=user.rid)
    flash(request, "User updated.")
    return RedirectResponse(f"/admin/users/{rid}", status_code=_REDIRECT)


def _user_action(
    request: Request,
    session: SessionDep,
    admin: User,
    rid: str,
    csrf: str,
) -> tuple[AdminService, User] | RedirectResponse:
    if not _check_csrf(request, csrf):
        return RedirectResponse(f"/admin/users/{rid}", status_code=_REDIRECT)
    svc = AdminService(session)
    user = svc.get_user(rid)
    if user is None:
        flash(request, "User not found.", "error")
        return RedirectResponse("/admin/users", status_code=_REDIRECT)
    return svc, user


@router.post("/users/{rid}/delete")
def user_delete(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    res = _user_action(request, session, admin, rid, csrf)
    if isinstance(res, RedirectResponse):
        return res
    svc, user = res
    if user.id == admin.id:
        flash(request, "You can't delete your own account here.", "error")
        return RedirectResponse(f"/admin/users/{rid}", status_code=_REDIRECT)
    svc.set_user_deleted(user, True)
    svc.log(admin, "user.soft_delete", target_type="user", target_rid=user.rid)
    flash(request, "User soft-deleted.", "warn")
    return RedirectResponse(f"/admin/users/{rid}", status_code=_REDIRECT)


@router.post("/users/{rid}/restore")
def user_restore(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    res = _user_action(request, session, admin, rid, csrf)
    if isinstance(res, RedirectResponse):
        return res
    svc, user = res
    svc.set_user_deleted(user, False)
    svc.log(admin, "user.restore", target_type="user", target_rid=user.rid)
    flash(request, "User restored.")
    return RedirectResponse(f"/admin/users/{rid}", status_code=_REDIRECT)


@router.post("/users/{rid}/reset-password")
def user_reset_password(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    new_password: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    res = _user_action(request, session, admin, rid, csrf)
    if isinstance(res, RedirectResponse):
        return res
    svc, user = res
    if len(new_password) < 8:
        flash(request, "Password must be at least 8 characters.", "error")
        return RedirectResponse(f"/admin/users/{rid}", status_code=_REDIRECT)
    svc.reset_password(user, new_password)
    svc.log(admin, "user.reset_password", target_type="user", target_rid=user.rid)
    flash(request, "Password reset.")
    return RedirectResponse(f"/admin/users/{rid}", status_code=_REDIRECT)


@router.post("/users/{rid}/unlink-google")
def user_unlink_google(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    res = _user_action(request, session, admin, rid, csrf)
    if isinstance(res, RedirectResponse):
        return res
    svc, user = res
    svc.unlink_google(user)
    svc.log(admin, "user.unlink_google", target_type="user", target_rid=user.rid)
    flash(request, "Google unlinked.")
    return RedirectResponse(f"/admin/users/{rid}", status_code=_REDIRECT)


# --- wallet detail + transactions ------------------------------------------


@router.get("/wallets/{rid}", response_class=HTMLResponse, response_model=None)
def wallet_detail(
    request: Request, session: SessionDep, admin: CurrentAdmin, rid: str
) -> HTMLResponse | RedirectResponse:
    svc = AdminService(session)
    wallet = svc.get_wallet(rid)
    if wallet is None:
        flash(request, "Wallet not found.", "error")
        return RedirectResponse("/admin/users", status_code=_REDIRECT)
    params = table_params(
        request, allowed_sorts=TRANSACTIONS_SORTS, default_sort="occurred_on"
    )
    page = svc.transactions_dt(params, wallet_id=wallet.id)
    return _table(
        request,
        admin,
        active="users",
        crumbs=[{"label": "Wallet"}, {"label": wallet.name}],
        page_template="wallet_detail.html",
        rows_template="_rows_wallet_txns.html",
        table_id="tbl-wallet-txns",
        endpoint=f"/admin/wallets/{wallet.rid}",
        columns=_WALLET_TXN_COLUMNS,
        page=page,
        wallet=wallet,
        balance=svc.wallet_balance(wallet),
    )


def _txn_form_ctx(
    request: Request,
    admin: User,
    svc: AdminService,
    wallet: Any,
    *,
    crumbs: list[dict[str, str]],
    txn: Any = None,
) -> dict[str, Any]:
    return _ctx(
        request,
        admin,
        "users",
        crumbs=crumbs,
        wallet=wallet,
        categories=svc.categories_for_wallet(wallet),
        txn=txn,
        amount_value=to_major(txn.amount, wallet.currency) if txn else "",
        today=date.today().isoformat(),
    )


@router.get(
    "/wallets/{rid}/transactions/new", response_class=HTMLResponse, response_model=None
)
def txn_new_form(
    request: Request, session: SessionDep, admin: CurrentAdmin, rid: str
) -> HTMLResponse | RedirectResponse:
    svc = AdminService(session)
    wallet = svc.get_wallet(rid)
    if wallet is None:
        flash(request, "Wallet not found.", "error")
        return RedirectResponse("/admin/users", status_code=_REDIRECT)
    return templates.TemplateResponse(
        request,
        "transaction_form.html",
        _txn_form_ctx(
            request,
            admin,
            svc,
            wallet,
            crumbs=[
                {"label": "Wallet", "href": f"/admin/wallets/{wallet.rid}"},
                {"label": "New transaction"},
            ],
        ),
    )


def _parse_txn_form(
    request: Request,
    wallet: Any,
    type_: str,
    amount: str,
    occurred_on: str,
) -> tuple[TransactionType, int, date] | None:
    if type_ not in (TransactionType.EXPENSE.value, TransactionType.INCOME.value):
        flash(request, "Pick income or expense.", "error")
        return None
    minor = to_minor(amount, wallet.currency)
    if minor is None or minor <= 0:
        flash(request, "Enter an amount greater than 0.", "error")
        return None
    try:
        on = date.fromisoformat(occurred_on) if occurred_on else date.today()
    except ValueError:
        flash(request, "Invalid date.", "error")
        return None
    return TransactionType(type_), minor, on


@router.post("/wallets/{rid}/transactions/new")
def txn_create(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    type_: Annotated[str, Form(alias="type")] = "",
    amount: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
    occurred_on: Annotated[str, Form()] = "",
    category_rid: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    wallet = svc.get_wallet(rid)
    if wallet is None:
        flash(request, "Wallet not found.", "error")
        return RedirectResponse("/admin/users", status_code=_REDIRECT)
    back = f"/admin/wallets/{wallet.rid}/transactions/new"
    if not _check_csrf(request, csrf):
        return RedirectResponse(back, status_code=_REDIRECT)
    parsed = _parse_txn_form(request, wallet, type_, amount, occurred_on)
    if parsed is None:
        return RedirectResponse(back, status_code=_REDIRECT)
    ttype, minor, on = parsed
    cat = svc.get_category(category_rid) if category_rid else None
    txn = svc.create_transaction(
        admin,
        wallet,
        type_=ttype,
        amount_minor=minor,
        note=note.strip() or None,
        occurred_on=on,
        category_id=cat.id if cat else None,
    )
    svc.log(admin, "txn.create", target_type="transaction", target_rid=txn.rid)
    flash(request, "Transaction created.")
    return RedirectResponse(f"/admin/wallets/{wallet.rid}", status_code=_REDIRECT)


@router.get("/transactions/{rid}/edit", response_class=HTMLResponse, response_model=None)
def txn_edit_form(
    request: Request, session: SessionDep, admin: CurrentAdmin, rid: str
) -> HTMLResponse | RedirectResponse:
    svc = AdminService(session)
    txn = svc.get_transaction(rid)
    if txn is None:
        flash(request, "Transaction not found.", "error")
        return RedirectResponse("/admin/users", status_code=_REDIRECT)
    if txn.transfer_group_rid:
        flash(request, "Transfers can't be edited — delete the pair instead.", "warn")
        return RedirectResponse(
            f"/admin/wallets/{txn.wallet.rid}", status_code=_REDIRECT
        )
    return templates.TemplateResponse(
        request,
        "transaction_form.html",
        _txn_form_ctx(
            request,
            admin,
            svc,
            txn.wallet,
            crumbs=[
                {"label": "Wallet", "href": f"/admin/wallets/{txn.wallet.rid}"},
                {"label": "Edit transaction"},
            ],
            txn=txn,
        ),
    )


@router.post("/transactions/{rid}/edit")
def txn_edit_submit(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    type_: Annotated[str, Form(alias="type")] = "",
    amount: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
    occurred_on: Annotated[str, Form()] = "",
    category_rid: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    txn = svc.get_transaction(rid)
    if txn is None:
        flash(request, "Transaction not found.", "error")
        return RedirectResponse("/admin/users", status_code=_REDIRECT)
    if txn.transfer_group_rid:
        flash(request, "Transfers can't be edited.", "warn")
        return RedirectResponse(
            f"/admin/wallets/{txn.wallet.rid}", status_code=_REDIRECT
        )
    back = f"/admin/transactions/{rid}/edit"
    if not _check_csrf(request, csrf):
        return RedirectResponse(back, status_code=_REDIRECT)
    parsed = _parse_txn_form(request, txn.wallet, type_, amount, occurred_on)
    if parsed is None:
        return RedirectResponse(back, status_code=_REDIRECT)
    ttype, minor, on = parsed
    cat = svc.get_category(category_rid) if category_rid else None
    svc.update_transaction(
        txn,
        txn.wallet,
        type_=ttype,
        amount_minor=minor,
        note=note.strip() or None,
        occurred_on=on,
        category_id=cat.id if cat else None,
    )
    svc.log(admin, "txn.edit", target_type="transaction", target_rid=txn.rid)
    flash(request, "Transaction updated.")
    return RedirectResponse(f"/admin/wallets/{txn.wallet.rid}", status_code=_REDIRECT)


@router.post("/transactions/{rid}/delete")
def txn_delete(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    txn = svc.get_transaction(rid)
    if txn is None:
        flash(request, "Transaction not found.", "error")
        return RedirectResponse("/admin/users", status_code=_REDIRECT)
    wallet_rid = txn.wallet.rid
    if not _check_csrf(request, csrf):
        return RedirectResponse(f"/admin/wallets/{wallet_rid}", status_code=_REDIRECT)
    removed = svc.delete_transaction(txn)
    svc.log(admin, "txn.delete", target_type="transaction", target_rid=rid)
    flash(request, f"Deleted {removed} transaction(s).", "warn")
    return RedirectResponse(f"/admin/wallets/{wallet_rid}", status_code=_REDIRECT)


@router.get("/transactions", response_class=HTMLResponse)
def transactions_page(
    request: Request, session: SessionDep, admin: CurrentAdmin
) -> HTMLResponse:
    params = table_params(
        request, allowed_sorts=TRANSACTIONS_SORTS, default_sort="occurred_on"
    )
    page = AdminService(session).transactions_dt(params)
    return _table(
        request,
        admin,
        active="transactions",
        crumbs=[{"label": "Transactions"}],
        page_template="transactions.html",
        rows_template="_rows_transactions.html",
        table_id="tbl-transactions",
        endpoint="/admin/transactions",
        columns=_TRANSACTIONS_COLUMNS,
        page=page,
    )


# --- family detail + management (P4) ---------------------------------------


@router.get("/families/{rid}", response_class=HTMLResponse, response_model=None)
def family_detail(
    request: Request, session: SessionDep, admin: CurrentAdmin, rid: str
) -> HTMLResponse | RedirectResponse:
    svc = AdminService(session)
    family = svc.get_family(rid)
    if family is None:
        flash(request, "Family not found.", "error")
        return RedirectResponse("/admin/families", status_code=_REDIRECT)

    def members_p() -> Any:
        return svc.family_members_page(
            family,
            table_params(
                request,
                allowed_sorts=_sort_keys(_FAMILY_MEMBER_COLUMNS),
                default_sort="display_name",
            ),
        )

    def wallets_p() -> Any:
        return svc.family_wallets_page(
            family,
            table_params(
                request,
                allowed_sorts=_sort_keys(_FAMILY_WALLET_COLUMNS),
                default_sort="name",
            ),
        )

    def categories_p() -> Any:
        return svc.family_categories_page(
            family,
            table_params(
                request,
                allowed_sorts=_sort_keys(_FAMILY_CATEGORY_COLUMNS),
                default_sort="name",
            ),
        )

    def budgets_p() -> Any:
        return svc.family_budgets_page(
            family,
            table_params(
                request,
                allowed_sorts=_sort_keys(_FAMILY_BUDGET_COLUMNS),
                default_sort="category",
            ),
        )

    if is_partial(request):
        table = request.query_params.get("table")
        if table == "members":
            return _fragment(
                request,
                rows_template="_rows_family_members.html",
                columns=_FAMILY_MEMBER_COLUMNS,
                page=members_p(),
            )
        if table == "wallets":
            return _fragment(
                request,
                rows_template="_rows_family_wallets.html",
                columns=_FAMILY_WALLET_COLUMNS,
                page=wallets_p(),
            )
        if table == "budgets":
            return _fragment(
                request,
                rows_template="_rows_family_budgets.html",
                columns=_FAMILY_BUDGET_COLUMNS,
                page=budgets_p(),
                family=family,
            )
        return _fragment(
            request,
            rows_template="_rows_family_categories.html",
            columns=_FAMILY_CATEGORY_COLUMNS,
            page=categories_p(),
            family=family,
        )

    return templates.TemplateResponse(
        request,
        "family_detail.html",
        _ctx(
            request,
            admin,
            "families",
            crumbs=[
                {"label": "Families", "href": "/admin/families"},
                {"label": family.name},
            ],
            family=family,
            kinds=[k.value for k in CategoryKind],
            categories=svc.family_categories_all(family),
            members_page=members_p(),
            members_columns=_FAMILY_MEMBER_COLUMNS,
            wallets_page=wallets_p(),
            wallets_columns=_FAMILY_WALLET_COLUMNS,
            categories_page=categories_p(),
            categories_columns=_FAMILY_CATEGORY_COLUMNS,
            budgets_page=budgets_p(),
            budgets_columns=_FAMILY_BUDGET_COLUMNS,
        ),
    )


def _load_family(
    request: Request, svc: AdminService, rid: str, csrf: str
) -> Any | RedirectResponse:
    if not _check_csrf(request, csrf):
        return RedirectResponse(f"/admin/families/{rid}", status_code=_REDIRECT)
    family = svc.get_family(rid)
    if family is None:
        flash(request, "Family not found.", "error")
        return RedirectResponse("/admin/families", status_code=_REDIRECT)
    return family


@router.post("/families/{rid}/rename")
def family_rename(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    name: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    family = _load_family(request, svc, rid, csrf)
    if isinstance(family, RedirectResponse):
        return family
    if not name.strip():
        flash(request, "Name is required.", "error")
    else:
        svc.rename_family(family, name)
        svc.log(admin, "family.rename", target_type="family", target_rid=family.rid)
        flash(request, "Family renamed.")
    return RedirectResponse(f"/admin/families/{rid}", status_code=_REDIRECT)


@router.post("/families/{rid}/delete")
def family_delete(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    family = _load_family(request, svc, rid, csrf)
    if isinstance(family, RedirectResponse):
        return family
    svc.set_family_deleted(family, True)
    svc.log(admin, "family.soft_delete", target_type="family", target_rid=family.rid)
    flash(request, "Family soft-deleted.", "warn")
    return RedirectResponse(f"/admin/families/{rid}", status_code=_REDIRECT)


@router.post("/families/{rid}/restore")
def family_restore(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    family = _load_family(request, svc, rid, csrf)
    if isinstance(family, RedirectResponse):
        return family
    svc.set_family_deleted(family, False)
    svc.log(admin, "family.restore", target_type="family", target_rid=family.rid)
    flash(request, "Family restored.")
    return RedirectResponse(f"/admin/families/{rid}", status_code=_REDIRECT)


# --- wallet edit / delete ---------------------------------------------------


@router.post("/wallets/{rid}/rename")
def wallet_rename(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    name: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    wallet = svc.get_wallet(rid)
    if wallet is None:
        flash(request, "Wallet not found.", "error")
        return RedirectResponse("/admin/users", status_code=_REDIRECT)
    if _check_csrf(request, csrf) and name.strip():
        svc.rename_wallet(wallet, name)
        svc.log(admin, "wallet.rename", target_type="wallet", target_rid=wallet.rid)
        flash(request, "Wallet renamed.")
    return RedirectResponse(f"/admin/wallets/{rid}", status_code=_REDIRECT)


@router.post("/wallets/{rid}/delete")
def wallet_delete(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    wallet = svc.get_wallet(rid)
    if wallet is None:
        flash(request, "Wallet not found.", "error")
        return RedirectResponse("/admin/users", status_code=_REDIRECT)
    if not _check_csrf(request, csrf):
        return RedirectResponse(f"/admin/wallets/{rid}", status_code=_REDIRECT)
    removed = svc.delete_wallet(wallet)
    svc.log(
        admin,
        "wallet.delete",
        target_type="wallet",
        target_rid=rid,
        detail=f"removed {removed} transactions",
    )
    flash(request, f"Wallet deleted ({removed} transactions removed).", "warn")
    return RedirectResponse("/admin/users", status_code=_REDIRECT)


# --- categories CRUD --------------------------------------------------------


@router.post("/families/{rid}/categories")
def category_add(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    name: Annotated[str, Form()] = "",
    icon: Annotated[str, Form()] = "",
    color: Annotated[str, Form()] = "",
    kind: Annotated[str, Form()] = CategoryKind.EXPENSE.value,
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    family = _load_family(request, svc, rid, csrf)
    if isinstance(family, RedirectResponse):
        return family
    if kind not in (CategoryKind.EXPENSE.value, CategoryKind.INCOME.value) or not name.strip():
        flash(request, "Name and a valid kind are required.", "error")
        return RedirectResponse(f"/admin/families/{rid}", status_code=_REDIRECT)
    cat = svc.add_category(family, name=name, icon=icon, color=color, kind=kind)
    svc.log(admin, "category.create", target_type="category", target_rid=cat.rid)
    flash(request, "Category added.")
    return RedirectResponse(f"/admin/families/{rid}", status_code=_REDIRECT)


@router.get("/categories/{rid}/edit", response_class=HTMLResponse, response_model=None)
def category_edit_form(
    request: Request, session: SessionDep, admin: CurrentAdmin, rid: str
) -> HTMLResponse | RedirectResponse:
    svc = AdminService(session)
    cat = svc.get_category(rid)
    if cat is None:
        flash(request, "Category not found.", "error")
        return RedirectResponse("/admin/families", status_code=_REDIRECT)
    family = svc.get_family_by_id(cat.family_id) if cat.family_id else None
    back = f"/admin/families/{family.rid}" if family else "/admin/families"
    return templates.TemplateResponse(
        request,
        "category_edit.html",
        _ctx(
            request,
            admin,
            "families",
            crumbs=[{"label": "Families", "href": "/admin/families"}, {"label": "Edit category"}],
            cat=cat,
            family_rid=family.rid if family else "",
            back=back,
        ),
    )


@router.post("/categories/{rid}/edit")
def category_edit(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    name: Annotated[str, Form()] = "",
    icon: Annotated[str, Form()] = "",
    color: Annotated[str, Form()] = "",
    family_rid: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    back = f"/admin/families/{family_rid}"
    cat = svc.get_category(rid)
    if cat is None:
        flash(request, "Category not found.", "error")
        return RedirectResponse(back, status_code=_REDIRECT)
    if _check_csrf(request, csrf) and name.strip():
        svc.update_category(cat, name=name, icon=icon, color=color)
        svc.log(admin, "category.edit", target_type="category", target_rid=cat.rid)
        flash(request, "Category updated.")
    return RedirectResponse(back, status_code=_REDIRECT)


@router.post("/categories/{rid}/delete")
def category_delete(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    family_rid: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    back = f"/admin/families/{family_rid}"
    cat = svc.get_category(rid)
    if cat is None:
        flash(request, "Category not found.", "error")
        return RedirectResponse(back, status_code=_REDIRECT)
    if _check_csrf(request, csrf):
        svc.delete_category(cat)
        svc.log(admin, "category.delete", target_type="category", target_rid=rid)
        flash(request, "Category deleted (its transactions are now uncategorized).", "warn")
    return RedirectResponse(back, status_code=_REDIRECT)


# --- budgets CRUD -----------------------------------------------------------


@router.post("/families/{rid}/budgets")
def budget_add(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    category_rid: Annotated[str, Form()] = "",
    amount: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    family = _load_family(request, svc, rid, csrf)
    if isinstance(family, RedirectResponse):
        return family
    cat = svc.get_category(category_rid) if category_rid else None
    minor = to_minor(amount, "VND")
    if cat is None or minor is None or minor <= 0:
        flash(request, "Pick a category and a positive amount.", "error")
        return RedirectResponse(f"/admin/families/{rid}", status_code=_REDIRECT)
    budget = svc.add_budget(family, category=cat, amount_base=minor, actor=admin)
    svc.log(admin, "budget.create", target_type="budget", target_rid=budget.rid)
    flash(request, "Budget added.")
    return RedirectResponse(f"/admin/families/{rid}", status_code=_REDIRECT)


@router.get("/budgets/{rid}/edit", response_class=HTMLResponse, response_model=None)
def budget_edit_form(
    request: Request, session: SessionDep, admin: CurrentAdmin, rid: str
) -> HTMLResponse | RedirectResponse:
    svc = AdminService(session)
    budget = svc.get_budget(rid)
    if budget is None:
        flash(request, "Budget not found.", "error")
        return RedirectResponse("/admin/families", status_code=_REDIRECT)
    family = svc.get_family_by_id(budget.family_id) if budget.family_id else None
    back = f"/admin/families/{family.rid}" if family else "/admin/families"
    return templates.TemplateResponse(
        request,
        "budget_edit.html",
        _ctx(
            request,
            admin,
            "families",
            crumbs=[{"label": "Families", "href": "/admin/families"}, {"label": "Edit budget"}],
            budget=budget,
            family_rid=family.rid if family else "",
            back=back,
        ),
    )


@router.post("/budgets/{rid}/edit")
def budget_edit(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    amount: Annotated[str, Form()] = "",
    family_rid: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    back = f"/admin/families/{family_rid}"
    budget = svc.get_budget(rid)
    if budget is None:
        flash(request, "Budget not found.", "error")
        return RedirectResponse(back, status_code=_REDIRECT)
    minor = to_minor(amount, "VND")
    if _check_csrf(request, csrf) and minor is not None and minor > 0:
        svc.update_budget(budget, minor)
        svc.log(admin, "budget.edit", target_type="budget", target_rid=budget.rid)
        flash(request, "Budget updated.")
    return RedirectResponse(back, status_code=_REDIRECT)


@router.post("/budgets/{rid}/delete")
def budget_delete(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
    rid: str,
    family_rid: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    svc = AdminService(session)
    back = f"/admin/families/{family_rid}"
    budget = svc.get_budget(rid)
    if budget is None:
        flash(request, "Budget not found.", "error")
        return RedirectResponse(back, status_code=_REDIRECT)
    if _check_csrf(request, csrf):
        svc.delete_budget(budget)
        svc.log(admin, "budget.delete", target_type="budget", target_rid=rid)
        flash(request, "Budget deleted.", "warn")
    return RedirectResponse(back, status_code=_REDIRECT)


# --- Ops: dependencies (Dependabot) ----------------------------------------


@router.get("/dependencies", response_class=HTMLResponse)
def dependencies_page(
    request: Request, session: SessionDep, admin: CurrentAdmin
) -> HTMLResponse:
    force = request.query_params.get("refresh") == "1"
    report = dependency_report(force=force)
    svc = AdminService(session)

    def alerts_page(alerts: list[dict[str, Any]]) -> Any:
        return svc.deps_alerts_page(
            alerts,
            table_params(
                request, allowed_sorts=_sort_keys(_DEPS_COLUMNS), default_sort="package"
            ),
        )

    if is_partial(request):
        repo_name = request.query_params.get("repo")
        alerts = next(
            (r["alerts"] for r in report["repos"] if r["repo"] == repo_name and r["ok"]),
            [],
        )
        return _fragment(
            request,
            rows_template="_rows_deps.html",
            columns=_DEPS_COLUMNS,
            page=alerts_page(alerts),
        )

    deps_pages = {
        r["repo"]: alerts_page(r["alerts"])
        for r in report["repos"]
        if r["ok"] and r["alerts"]
    }
    return templates.TemplateResponse(
        request,
        "deps.html",
        _ctx(
            request,
            admin,
            "deps",
            crumbs=[{"label": "Dependencies"}],
            report=report,
            libs=library_report(force=force),
            deps_pages=deps_pages,
            deps_columns=_DEPS_COLUMNS,
        ),
    )


def setup_admin(app: FastAPI) -> None:
    """Wire the admin panel into the app: session middleware, the login-required
    redirect handler, and the router. Call from ``app.main`` before the SPA mount.
    """
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.admin_session_secret,
        session_cookie="famo_admin",
        max_age=settings.admin_session_max_age,
        same_site="lax",
        https_only=settings.env == "production",
    )

    @app.exception_handler(AdminLoginRequired)
    async def _login_required(
        request: Request, exc: AdminLoginRequired
    ) -> RedirectResponse:
        return RedirectResponse(LOGIN_PATH, status_code=_REDIRECT)

    # Compile the SCSS, expose its cache-busting URL to templates, and serve the
    # compiled file. Mounted before the SPA catch-all at "/" (this runs first in
    # app.main), so /admin/static/* resolves here.
    version = _build_admin_css()
    templates.env.globals["admin_css_url"] = f"/admin/static/admin.css?v={version}"
    app.mount("/admin/static", StaticFiles(directory=str(_STATIC_DIR)), name="admin-static")

    app.include_router(router)
