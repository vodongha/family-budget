"""Google ID token verification.

Isolated here so the auth service depends on a small, mockable function rather
than the google-auth library directly (tests monkeypatch ``verify_google_id_token``).
"""

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token


class GoogleAuthError(Exception):
    """The Google ID token was missing, malformed, or failed verification."""


def verify_google_id_token(token: str, client_ids: list[str]) -> dict[str, str]:
    """Verify a Google ID token and return its claims.

    Checks the signature against Google's public keys and that the audience is
    one of our configured client IDs. Raises [GoogleAuthError] on any problem.
    Returns the relevant claims: ``sub``, ``email``, ``email_verified``, ``name``.
    """
    if not token:
        raise GoogleAuthError("Missing Google ID token")
    if not client_ids:
        raise GoogleAuthError("Google login is not configured")
    try:
        claims = google_id_token.verify_oauth2_token(
            token, google_requests.Request()
        )
    except ValueError as exc:
        raise GoogleAuthError(str(exc)) from exc

    if claims.get("aud") not in client_ids:
        raise GoogleAuthError("Token audience does not match this app")
    if not claims.get("email"):
        raise GoogleAuthError("Token has no email")
    return claims
