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
from app.domains.admin.deps_panel import dependency_report
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
from app.domains.categories.models import CategoryKind
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


@router.get("/wallets/{rid}", response_class=HTMLResponse, response_model=None)
def wallet_detail(
    request: Request, session: SessionDep, admin: CurrentAdmin, rid: str
) -> HTMLResponse | RedirectResponse:
    svc = AdminService(session)
    wallet = svc.get_wallet(rid)
    if wallet is None:
        flash(request, "Wallet not found.", "error")
        return RedirectResponse("/admin/users", status_code=_REDIRECT)
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
            txns=svc.transactions_all(wallet_id=wallet.id),
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
    return templates.TemplateResponse(
        request,
        "transactions.html",
        _ctx(
            request,
            admin,
            "transactions",
            crumbs=[{"label": "Transactions"}],
            txns=svc.transactions_all(),
        ),
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
    overview = svc.family_overview(family)
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
            **overview,
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
    return templates.TemplateResponse(
        request,
        "deps.html",
        _ctx(
            request,
            admin,
            "deps",
            crumbs=[{"label": "Dependencies"}],
            report=dependency_report(force=force),
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
