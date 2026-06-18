"""Admin panel routes — server-rendered (Jinja2), session-authenticated.

Mounted under ``/admin``. Registered before the SPA static mount in
``app.main`` so these paths win over the Flutter web app served at ``/``.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_303_SEE_OTHER

from app.core.config import settings
from app.core.deps import SessionDep
from app.domains.admin.security import (
    LOGIN_PATH,
    AdminCsrfError,
    AdminLoginRequired,
    CurrentAdmin,
    csrf_token,
    login_admin,
    logout_admin,
    verify_csrf,
)
from app.domains.admin.service import AdminService

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(prefix="/admin", tags=["admin"], include_in_schema=False)


def _is_logged_in(request: Request, session: SessionDep) -> bool:
    rid = request.session.get("admin_rid")
    return bool(rid and AdminService(session).get_active_admin(rid))


@router.get("/login", response_class=HTMLResponse, response_model=None)
def login_form(request: Request, session: SessionDep) -> HTMLResponse | RedirectResponse:
    if _is_logged_in(request, session):
        return RedirectResponse("/admin", status_code=HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"csrf": csrf_token(request), "error": None},
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
        return RedirectResponse(LOGIN_PATH, status_code=HTTP_303_SEE_OTHER)
    user = AdminService(session).authenticate(email, password)
    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"csrf": csrf_token(request), "error": "Invalid credentials"},
            status_code=401,
        )
    login_admin(request, user)
    return RedirectResponse("/admin", status_code=HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(
    request: Request,
    csrf: Annotated[str, Form()] = "",
) -> RedirectResponse:
    # Best-effort CSRF; even without it, logout is non-destructive.
    try:
        verify_csrf(request, csrf)
    except AdminCsrfError:
        pass
    logout_admin(request)
    return RedirectResponse(LOGIN_PATH, status_code=HTTP_303_SEE_OTHER)


@router.get("", response_class=HTMLResponse)
def dashboard(
    request: Request,
    session: SessionDep,
    admin: CurrentAdmin,
) -> HTMLResponse:
    data = AdminService(session).dashboard()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "admin": admin,
            "csrf": csrf_token(request),
            "active": "dashboard",
            **data,
        },
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
        return RedirectResponse(LOGIN_PATH, status_code=HTTP_303_SEE_OTHER)

    app.include_router(router)
