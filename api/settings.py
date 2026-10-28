"""Environment-driven settings. Every variable is listed in .env.example."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    env: str = os.environ.get("CONSTAT_ENV", "dev")
    database_url: str = os.environ.get("DATABASE_URL", "sqlite:///data/sidecar.db")
    claim_store: str = os.environ.get("CLAIM_STORE", "file")          # file | atlan
    claim_store_path: str = os.environ.get("CLAIM_STORE_PATH", "data/claims")
    atlan_glossary: str = os.environ.get("ATLAN_GLOSSARY", "Security Claims")
    atlan_jwks_url: str = os.environ.get("ATLAN_JWKS_URL", "")
    atlan_jwt_public_key: str = os.environ.get("ATLAN_JWT_PUBLIC_KEY", "")
    atlan_issuer: str = os.environ.get("ATLAN_ISSUER", "")
    atlan_audience: str = os.environ.get("CONSTAT_ATLAN_AUDIENCE", "constat")
    dev_jwt_secret: str = os.environ.get("CONSTAT_DEV_JWT_SECRET", "")
    dev_token: str = os.environ.get("CONSTAT_DEV_TOKEN", "")
    default_tenant: str = os.environ.get("CONSTAT_TENANT", "constat")
    cors_origins: str = os.environ.get("CONSTAT_CORS_ORIGINS", "http://localhost:3000")

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    def ensure_dirs(self) -> None:
        if self.database_url.startswith("sqlite:///") and ":memory:" not in self.database_url:
            Path(self.database_url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
        if self.claim_store == "file":
            Path(self.claim_store_path).mkdir(parents=True, exist_ok=True)


def load() -> Settings:
    return Settings()
