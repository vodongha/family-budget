"""Password hashing (bcrypt) and JWT creation/verification."""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def hash_password(plain: str) -> str:
    # bcrypt hashes at most the first 72 bytes of the input — a property of the
    # algorithm, not a bug. Adequate for normal passwords.
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    """``subject`` is the user's ULID (rid). ``extra`` carries claims like family_id."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Return the decoded claims, or None if the token is invalid/expired."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
