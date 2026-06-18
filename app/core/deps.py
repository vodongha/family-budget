"""Shared FastAPI dependencies: DB session, current user, current family (tenant scope)."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.currency import BASE_CURRENCY, is_supported
from app.core.database import get_session
from app.core.security import decode_access_token
from app.domains.users.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

SessionDep = Annotated[Session, Depends(get_session)]
TokenDep = Annotated[str, Depends(oauth2_scheme)]

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    claims = decode_access_token(token)
    if claims is None:
        raise _CREDENTIALS_ERROR
    rid = claims.get("sub")
    if not rid:
        raise _CREDENTIALS_ERROR
    user = session.scalar(select(User).where(User.rid == rid))
    # A soft-deleted account must not be usable even with a still-valid token.
    if user is None or user.is_deleted:
        raise _CREDENTIALS_ERROR
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_family(current_user: CurrentUser) -> int:
    """The multi-tenant boundary: every scoped query must filter by this family_id.

    Mirrors konfipay's CurrentUUID — repositories always receive it explicitly so
    services stay stateless.
    """
    if current_user.family_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not attached to a family",
        )
    return current_user.family_id


CurrentFamily = Annotated[int, Depends(get_current_family)]


def get_optional_family(current_user: CurrentUser) -> int | None:
    """The caller's family_id, or ``None`` when they don't belong to one.

    For endpoints that also serve the **personal** space (wallets, transactions,
    dashboard, stats), which works without a family. Personal data is scoped by
    the user, not the family; family scope is empty when this is ``None``.
    """
    return current_user.family_id


OptionalFamily = Annotated[int | None, Depends(get_optional_family)]


def get_display_currency(display_currency: str = BASE_CURRENCY) -> str:
    """A query param: the ISO-4217 currency to render cross-wallet totals in.

    Per-wallet balances always stay in their own currency; only aggregates
    (dashboard/stats/budget totals) are converted to this. Defaults to the base
    currency; an unsupported code is a 422 so the client can't silently mislabel
    figures."""
    code = display_currency.upper()
    if not is_supported(code):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported currency: {display_currency}",
        )
    return code


DisplayCurrency = Annotated[str, Depends(get_display_currency)]
