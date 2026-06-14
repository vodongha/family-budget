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

    # Google Sign-In — the OAuth client ID(s) the backend accepts as the audience
    # of incoming Google ID tokens. Comma-separated to allow web + Android + iOS
    # client IDs at once. Empty disables Google login.
    google_client_id: str = ""

    # JWT
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

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
