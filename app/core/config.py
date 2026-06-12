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

    # JWT
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Infra
    redis_url: str = "redis://redis:6379/0"
    env: str = "development"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — settings are read once per process."""
    return Settings()


settings = get_settings()
