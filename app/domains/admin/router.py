"""Admin panel routes — server-rendered (Jinja2), session-authenticated.

Mounted under ``/admin``. Registered before the SPA static mount in
``app.main`` so these paths win over the Flutter web app served at ``/``.
"""

from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_303_SEE_OTHER

from app.core.config import settings
from app.core.deps import SessionDep
from app.domains.admin.money import to_major, to_minor
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
from app.domains.transactions.models import TransactionType
from app.domains.users.models import User, UserRole

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.filters["money"] = to_major

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
    data = AdminService(session).dashboard()
    return templates.TemplateResponse(
        request, "dashboard.html", _ctx(request, admin, "dashboard", **data)
    )


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, session: SessionDep, admin: CurrentAdmin) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "users.html",
        _ctx(
            request,
            admin,
            "users",
            crumbs=[{"label": "Users"}],
            users=AdminService(session).list_users(),
        ),
    )


@router.get("/families", response_class=HTMLResponse)
def families_page(
    request: Request, session: SessionDep, admin: CurrentAdmin
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "families.html",
        _ctx(
            request,
            admin,
            "families",
            crumbs=[{"label": "Families"}],
            rows=AdminService(session).list_families(),
        ),
    )


@router.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, session: SessionDep, admin: CurrentAdmin) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "audit.html",
        _ctx(
            request,
            admin,
            "audit",
            crumbs=[{"label": "Audit log"}],
            entries=AdminService(session).recent_audit(limit=500),
        ),
    )


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
    wallets = svc.user_wallets(user)
    txns = svc.transactions(created_by_user_id=user.id, page=1, per_page=10)
    return templates.TemplateResponse(
        request,
        "user_detail.html",
        _ctx(
            request,
            admin,
            "users",
            crumbs=[{"label": "Users", "href": "/admin/users"}, {"label": user.email}],
            user=user,
            wallets=wallets,
            txns=txns["rows"],
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


def _page_arg(request: Request) -> int:
    try:
        return max(1, int(request.query_params.get("page", "1")))
    except ValueError:
        return 1


@router.get("/wallets/{rid}", response_class=HTMLResponse, response_model=None)
def wallet_detail(
    request: Request, session: SessionDep, admin: CurrentAdmin, rid: str
) -> HTMLResponse | RedirectResponse:
    svc = AdminService(session)
    wallet = svc.get_wallet(rid)
    if wallet is None:
        flash(request, "Wallet not found.", "error")
        return RedirectResponse("/admin/users", status_code=_REDIRECT)
    page = _page_arg(request)
    data = svc.transactions(wallet_id=wallet.id, page=page, per_page=25)
    return templates.TemplateResponse(
        request,
        "wallet_detail.html",
        _ctx(
            request,
            admin,
            "users",
            crumbs=[{"label": "Wallet"}, {"label": wallet.name}],
            wallet=wallet,
            balance=svc.wallet_balance(wallet),
            data=data,
            base_url=f"/admin/wallets/{wallet.rid}",
        ),
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
    svc = AdminService(session)
    page = _page_arg(request)
    type_ = request.query_params.get("type") or None
    if type_ not in (None, "expense", "income", "transfer_in", "transfer_out"):
        type_ = None
    data = svc.transactions(type_=type_, page=page, per_page=30)
    return templates.TemplateResponse(
        request,
        "transactions.html",
        _ctx(
            request,
            admin,
            "transactions",
            crumbs=[{"label": "Transactions"}],
            data=data,
            type_=type_ or "",
            base_url="/admin/transactions",
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

    app.include_router(router)
