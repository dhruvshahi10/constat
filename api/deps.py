"""Process-wide singletons behind FastAPI dependencies, overridable in tests."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from constat.claims import ClaimStore, FileClaimStore
from constat.claims.match import ClaimMatcher
from constat.persist import Repository, make_repo

from .settings import Settings, load


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = load()
    s.ensure_dirs()
    return s


@lru_cache(maxsize=1)
def get_repo() -> Repository:
    return make_repo(get_settings().database_url)


@lru_cache(maxsize=1)
def get_claim_store() -> ClaimStore:
    s = get_settings()
    if s.claim_store == "atlan":
        from constat.claims.atlan import AtlanClaimStore
        return AtlanClaimStore(s.atlan_glossary, Path(s.claim_store_path) / "sidecar")
    return FileClaimStore(Path(s.claim_store_path))


def get_matcher() -> ClaimMatcher:
    return ClaimMatcher(get_claim_store())


def reset() -> None:
    """Tests call this between apps."""
    get_settings.cache_clear()
    get_repo.cache_clear()
    get_claim_store.cache_clear()
