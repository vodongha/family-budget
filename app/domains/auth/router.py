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
    InvalidPhoneError,
    OwnerMustTransferError,
    PhoneAlreadyInUseError,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_PHONE = HTTPException(
    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    detail="Invalid phone number",
)
_PHONE_TAKEN = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="Phone number already in use",
)


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new family + owner",
)
def register(payload: RegisterRequest, session: SessionDep) -> UserRead:
    """Create a new family and its first user (the **owner**). Does not log you
    in — call `POST /auth/login` afterwards. Phone is optional (E.164)."""
    service = AuthService(session)
    try:
        user = service.register(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            family_name=payload.family_name,
            phone=payload.phone,
        )
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from None
    except InvalidPhoneError:
        raise _INVALID_PHONE from None
    except PhoneAlreadyInUseError:
        raise _PHONE_TAKEN from None
    return UserRead.model_validate(user)


@router.post("/login", response_model=Token, summary="Sign in (password)")
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> Token:
    """OAuth2 password flow (form-encoded). Send your email as `username` and your
    password; returns a JWT `access_token` to use as a `Bearer` token."""
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


@router.post("/google", response_model=Token, summary="Sign in with Google")
def google_login(payload: GoogleLoginRequest, session: SessionDep) -> Token:
    """Sign in / sign up with a Google ID token obtained on the client. Links the
    Google account to an existing user by email, or creates a new family + owner."""
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


@router.get("/me", response_model=UserRead, summary="Get my profile")
def me(current_user: CurrentUser) -> UserRead:
    """Return the signed-in user, including `role` (`owner`/`member`) and phone."""
    return UserRead.model_validate(current_user)


@router.patch("/me", response_model=UserRead, summary="Update my profile")
def update_me(
    payload: UpdateProfileRequest, current_user: CurrentUser, session: SessionDep
) -> UserRead:
    """Update display name and optional phone (E.164). A blank phone clears it;
    `422` if the number is invalid, `409` if it belongs to another account."""
    service = AuthService(session)
    try:
        user = service.update_profile(
            current_user, payload.display_name.strip(), payload.phone
        )
    except InvalidPhoneError:
        raise _INVALID_PHONE from None
    except PhoneAlreadyInUseError:
        raise _PHONE_TAKEN from None
    return UserRead.model_validate(user)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete my account",
)
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
