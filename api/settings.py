"""Environment-driven settings. Every variable is listed in .env.example."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    env: str
    database_url: str
    claim_store: str
    claim_store_path: str
    atlan_glossary: str
    atlan_jwks_url: str
    atlan_jwt_public_key: str
    atlan_issuer: str
    atlan_audience: str
    dev_jwt_secret: str
    dev_token: str
    default_tenant: str
    tenants: str
    expose_docs: str
    cors_origins: str

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    @property
    def allowed_tenants(self) -> set[str]:
        extra = {t.strip() for t in self.tenants.split(",") if t.strip()}
        return extra | {self.default_tenant}

    def check(self) -> list[str]:
        """Configuration problems that must stop a non-dev process."""
        problems = []
        if not self.is_dev:
            if self.dev_token:
                problems.append("CONSTAT_DEV_TOKEN is set outside dev")
            if self.dev_jwt_secret:
                problems.append("CONSTAT_DEV_JWT_SECRET is set outside dev")
            if (self.atlan_jwks_url or self.atlan_jwt_public_key) and not self.atlan_issuer:
                problems.append("ATLAN_ISSUER is required when Atlan JWTs are accepted outside dev")
        return problems

    def ensure_dirs(self) -> None:
        if self.database_url.startswith("sqlite:///") and ":memory:" not in self.database_url:
            Path(self.database_url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
        if self.claim_store == "file":
            Path(self.claim_store_path).mkdir(parents=True, exist_ok=True)


def load() -> Settings:
    """Read the environment now, not at import time, so tests and restarts see
    the current values."""
    e = os.environ.get
    return Settings(
        env=e("CONSTAT_ENV", "prod"),                      # dev must be asked for explicitly
        database_url=e("DATABASE_URL", "sqlite:///data/sidecar.db"),
        claim_store=e("CLAIM_STORE", "file"),
        claim_store_path=e("CLAIM_STORE_PATH", "data/claims"),
        atlan_glossary=e("ATLAN_GLOSSARY", "Security Claims"),
        atlan_jwks_url=e("ATLAN_JWKS_URL", ""),
        atlan_jwt_public_key=e("ATLAN_JWT_PUBLIC_KEY", ""),
        atlan_issuer=e("ATLAN_ISSUER", ""),
        atlan_audience=e("CONSTAT_ATLAN_AUDIENCE", "constat"),
        dev_jwt_secret=e("CONSTAT_DEV_JWT_SECRET", ""),
        dev_token=e("CONSTAT_DEV_TOKEN", ""),
        default_tenant=e("CONSTAT_TENANT", "constat"),
        tenants=e("CONSTAT_TENANTS", ""),
        expose_docs=e("CONSTAT_EXPOSE_DOCS", ""),
        cors_origins=e("CONSTAT_CORS_ORIGINS", "http://localhost:3000"),
    )
