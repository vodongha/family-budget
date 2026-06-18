"""Admin session auth + CSRF — the gate for every ``/admin`` route.

Auth is a signed session cookie (Starlette ``SessionMiddleware``), independent of
the app's bearer JWT. The session stores only the admin's ``rid``; the user is
re-loaded and re-checked on every request, so revoking ``is_superadmin`` or
deleting the account immediately invalidates a live session.
"""

import secrets
from typing import Annotated

from fastapi import Depends, Request
from starlette.status import HTTP_303_SEE_OTHER

from app.core.deps import SessionDep
from app.domains.admin.service import AdminService
from app.domains.users.models import User

_SESSION_RID_KEY = "admin_rid"
_SESSION_CSRF_KEY = "admin_csrf"


class AdminLoginRequired(Exception):
    """Raised when an admin route is hit without a valid admin session. An app
    exception handler turns this into a redirect to the login page."""


class AdminCsrfError(Exception):
    """Raised when a POST is missing or has a mismatched CSRF token."""


def login_admin(request: Request, user: User) -> None:
    """Mark the session as authenticated for ``user`` and rotate the CSRF token."""
    request.session[_SESSION_RID_KEY] = user.rid
    request.session[_SESSION_CSRF_KEY] = secrets.token_urlsafe(32)


def logout_admin(request: Request) -> None:
    request.session.clear()


_SESSION_FLASH_KEY = "admin_flash"


def flash(request: Request, message: str, kind: str = "ok") -> None:
    """Queue a one-shot message (``kind`` = ok|warn|error) shown after the next
    redirect, then cleared."""
    msgs = request.session.get(_SESSION_FLASH_KEY, [])
    msgs.append({"message": message, "kind": kind})
    request.session[_SESSION_FLASH_KEY] = msgs


def pop_flashes(request: Request) -> list[dict[str, str]]:
    msgs = request.session.get(_SESSION_FLASH_KEY, [])
    if msgs:
        request.session[_SESSION_FLASH_KEY] = []
    return msgs


def csrf_token(request: Request) -> str:
    """The session's CSRF token, creating one if absent (e.g. on the login page
    before authenticating)."""
    token = request.session.get(_SESSION_CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[_SESSION_CSRF_KEY] = token
    return token


def verify_csrf(request: Request, submitted: str | None) -> None:
    expected = request.session.get(_SESSION_CSRF_KEY)
    if not expected or not submitted or not secrets.compare_digest(
        submitted, expected
    ):
        raise AdminCsrfError()


def require_admin(request: Request, session: SessionDep) -> User:
    """Dependency: the current super-admin, or raise [AdminLoginRequired]."""
    rid = request.session.get(_SESSION_RID_KEY)
    if not rid:
        raise AdminLoginRequired()
    user = AdminService(session).get_active_admin(rid)
    if user is None:
        request.session.clear()
        raise AdminLoginRequired()
    return user


CurrentAdmin = Annotated[User, Depends(require_admin)]

# The path the login-required handler redirects to.
LOGIN_PATH = "/admin/login"
REDIRECT_STATUS = HTTP_303_SEE_OTHER
