"""Application settings, loaded from environment / .env via pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Oracle ADB (thin mode, wallet)
    oracle_user: str = "ADMIN"
    oracle_password: str = ""
    oracle_dsn: str = ""
    wallet_dir: str = "/app/wallet"
    wallet_password: str = ""
    # Optional schema to own this app's tables, so several apps can share one ADB
    # without colliding (each app gets its own schema). When set, every connection
    # runs ``ALTER SESSION SET CURRENT_SCHEMA`` to it, so Alembic and the ORM
    # create/read tables there instead of the connecting user's default schema.
    # Empty → use the connecting user's own schema (back-compat).
    oracle_schema: str = ""

    # Google Sign-In — the OAuth client ID(s) the backend accepts as the audience
    # of incoming Google ID tokens. Comma-separated to allow web + Android + iOS
    # client IDs at once. Empty disables Google login.
    google_client_id: str = ""

    # JWT. The session is meant to last until the user explicitly logs out, so the
    # access token is long-lived (~10 years). The app still drops the token and
    # returns to login on any 401.
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 365 * 10

    # Admin panel (/admin) — a server-rendered, session-cookie-authenticated
    # surface, separate from the app's JWT. Set a strong random value in
    # production; the signed session cookie is only as safe as this secret.
    admin_session_secret: str = "change-me-admin"
    # Idle lifetime of the admin session cookie, in seconds (default 8 hours).
    admin_session_max_age: int = 60 * 60 * 8

    # Admin "Dependencies" panel — reads GitHub Dependabot alerts for these repos
    # (outdated / vulnerable libraries). Needs a token with read access to the
    # repos' Dependabot alerts (classic `repo`/`security_events`, or a fine-grained
    # token with "Dependabot alerts: read"). Empty → the panel shows a setup hint.
    github_token: str = ""
    github_repos: str = "vodongha/family-budget,vodongha/family-budget-app"

    @property
    def github_repo_list(self) -> list[str]:
        return [r.strip() for r in self.github_repos.split(",") if r.strip()]

    # Infra
    redis_url: str = "redis://redis:6379/0"
    env: str = "development"

    # CORS — comma-separated allowed origins for the browser (web) client.
    # "*" allows any origin (fine while there's no fixed web domain); set this to
    # the real web origin(s) in production, e.g. "https://app.famo.io.vn".
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — settings are read once per process."""
    return Settings()


settings = get_settings()
