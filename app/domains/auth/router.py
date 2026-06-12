"""Auth routes — thin: parse request, delegate to service, shape response."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.deps import CurrentUser, SessionDep
from app.core.google import GoogleAuthError
from app.domains.auth.schemas import (
    GoogleLoginRequest,
    RegisterRequest,
    Token,
    UpdateProfileRequest,
    UserRead,
)
from app.domains.auth.service import (
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    OwnerMustTransferError,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, session: SessionDep) -> UserRead:
    service = AuthService(session)
    try:
        user = service.register(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            family_name=payload.family_name,
        )
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from None
    return UserRead.model_validate(user)


@router.post("/login", response_model=Token)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> Token:
    service = AuthService(session)
    try:
        # OAuth2 form uses `username`; we treat it as the email.
        user = service.authenticate(form.username, form.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return Token(access_token=service.issue_token(user))


@router.post("/google", response_model=Token)
def google_login(payload: GoogleLoginRequest, session: SessionDep) -> Token:
    """Sign in / sign up with a Google ID token obtained on the client."""
    service = AuthService(session)
    try:
        user = service.google_login(payload.id_token)
    except GoogleAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return Token(access_token=service.issue_token(user))


@router.get("/me", response_model=UserRead)
def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.patch("/me", response_model=UserRead)
def update_me(
    payload: UpdateProfileRequest, current_user: CurrentUser, session: SessionDep
) -> UserRead:
    service = AuthService(session)
    user = service.update_display_name(current_user, payload.display_name.strip())
    return UserRead.model_validate(user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(current_user: CurrentUser, session: SessionDep) -> Response:
    """Self-service account deletion (Google Play policy). Soft-deletes the
    account immediately; data is purged by a scheduled job after the retention
    window."""
    service = AuthService(session)
    try:
        service.delete_account(current_user)
    except OwnerMustTransferError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You are the family owner. Transfer ownership to another member "
                "before deleting your account."
            ),
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
