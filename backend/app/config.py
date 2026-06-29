"""Central configuration loaded from environment variables."""
from __future__ import annotations

import os
from functools import lru_cache


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Config:
    def __init__(self) -> None:
        self.APP_ENV = os.environ.get("APP_ENV", "production")
        self.LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

        # Database
        self.PG_USER = os.environ.get("POSTGRES_USER", "watchvault")
        self.PG_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "change-me")
        self.PG_DB = os.environ.get("POSTGRES_DB", "watchvault")
        self.PG_HOST = os.environ.get("POSTGRES_HOST", "db")
        self.PG_PORT = os.environ.get("POSTGRES_PORT", "5432")

        # Auth / WebAuthn relying party
        self.RP_ID = os.environ.get("RP_ID", "localhost")
        self.RP_NAME = os.environ.get("RP_NAME", "WatchVault")
        self.RP_ORIGINS = _split(os.environ.get("RP_ORIGINS", "http://localhost:7210"))
        self.SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-insecure-secret")
        self.SESSION_TTL_HOURS = int(os.environ.get("SESSION_TTL_HOURS", "24"))
        self.SESSION_COOKIE = "wv_session"
        self.REGISTRATION_INVITE_CODE = os.environ.get("REGISTRATION_INVITE_CODE", "")

        # Metadata
        self.TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")

        # Paths
        self.DATA_DIR = os.environ.get("DATA_DIR", "/data")

    @property
    def dsn(self) -> str:
        return (
            f"host={self.PG_HOST} port={self.PG_PORT} dbname={self.PG_DB} "
            f"user={self.PG_USER} password={self.PG_PASSWORD}"
        )

    @property
    def is_secure_origin(self) -> bool:
        return any(o.startswith("https://") for o in self.RP_ORIGINS)


@lru_cache
def get_config() -> Config:
    return Config()
