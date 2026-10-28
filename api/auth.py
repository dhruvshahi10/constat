"""Who is calling. Two front doors, one Principal.

Bearer tokens (`t.<tenant>.<random>`) reuse constat.server.auth: hashed at
rest, constant-time compared, tenant carried inside the token. Atlan JWTs
arrive from the embedded-app handshake; they are verified against the tenant's
JWKS (or a pinned public key) and mapped to a principal by email. In dev a
shared secret signs HS256 tokens for the shell simulator, and a dev token
grants admin. Neither dev path exists outside CONSTAT_ENV=dev.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, Request

from constat.persist import Principal, Repository, ulid
from constat.server.auth import SLUG_RE, mint_token, token_slug

from .deps import get_repo, get_settings
from .settings import Settings

ROLES = ("reviewer", "owner", "admin")
_RANK = {r: i for i, r in enumerate(ROLES)}


@dataclass(frozen=True)
class CallerPrincipal:
    subject: str
    email: str
    role: str
    tenant: str
    source: str            # bearer | atlan_jwt | dev

    def at_least(self, role: str) -> bool:
        return _RANK[self.role] >= _RANK[role]


def _unauthorised(msg: str = "unauthorised") -> HTTPException:
    return HTTPException(status_code=401, detail={"error": msg, "code": "UNAUTHORISED"})


def create_principal(repo: Repository, tenant: str, email: str, role: str) -> tuple[Principal, str]:
    """Mint a bearer principal. Returns (principal, token). The token is shown
    once and never stored."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    if not SLUG_RE.match(tenant):
        raise ValueError("tenant must be a slug")
    token, token_hash = mint_token(tenant)
    p = Principal(id=ulid(), tenant=tenant, email=email, role=role, token_hash=token_hash,
                  source="bearer")
    repo.insert("principals", p)
    return p, token


def _bearer_principal(token: str, repo: Repository) -> Optional[CallerPrincipal]:
    tenant = token_slug(token)
    if tenant is None:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    for p in repo.list("principals", {"tenant": tenant, "token_hash": digest}, limit=1):
        return CallerPrincipal(subject=p.id, email=p.email, role=p.role, tenant=p.tenant,
                               source="bearer")
    return None


def verify_atlan_jwt(token: str, settings: Settings) -> dict:
    """Decode and verify an Atlan-issued JWT. RS256 via JWKS or a pinned key in
    production; HS256 with the dev secret only in dev."""
    import jwt  # PyJWT

    options = {"require": ["exp"]}
    kwargs: dict = {"audience": settings.atlan_audience} if settings.atlan_audience else {}
    if settings.atlan_issuer:
        kwargs["issuer"] = settings.atlan_issuer
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "")
        if alg == "HS256":
            if not (settings.is_dev and settings.dev_jwt_secret):
                raise _unauthorised("HS256 tokens are accepted only in dev")
            if len(settings.dev_jwt_secret.encode()) < 32:
                raise _unauthorised("dev JWT secret must be at least 32 bytes (RFC 7518 section 3.2)")
            return jwt.decode(token, settings.dev_jwt_secret, algorithms=["HS256"],
                              options=options, **kwargs)
        if not settings.is_dev and not settings.atlan_issuer:
            raise _unauthorised("ATLAN_ISSUER is not configured")
        if settings.atlan_jwks_url:
            key = _jwks_client(settings.atlan_jwks_url).get_signing_key_from_jwt(token).key
        elif settings.atlan_jwt_public_key:
            key = settings.atlan_jwt_public_key
        else:
            raise _unauthorised("no Atlan JWT verification key configured")
        return jwt.decode(token, key, algorithms=["RS256", "ES256"], options=options, **kwargs)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 - any verification failure is a 401
        raise _unauthorised(f"invalid token: {type(e).__name__}") from e


@lru_cache(maxsize=4)
def _jwks_client(url: str):
    import jwt
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=600, timeout=5)


def _jwt_principal(token: str, repo: Repository, settings: Settings) -> CallerPrincipal:
    claims = verify_atlan_jwt(token, settings)
    email = str(claims.get("email") or claims.get("preferred_username") or "")
    sub = str(claims.get("sub") or "")
    if not email and not sub:
        raise _unauthorised("token carries no identity")
    email = email or sub
    tenant = str(claims.get("tenant") or settings.default_tenant)
    # the tenant claim selects a data scope and a directory: it must be a slug and on the allowlist
    if not SLUG_RE.match(tenant) or tenant not in settings.allowed_tenants:
        raise _unauthorised("token tenant is not served by this deployment")
    # principals from JWTs are matched by source so a token cannot inherit a bearer principal's role
    existing = repo.list("principals", {"tenant": tenant, "email": email, "source": "atlan_jwt"}, limit=1)
    if existing:
        p = existing[0]
    else:
        # first sight of an Atlan user: reviewer by default, promoted by an admin
        p = Principal(id=ulid(), tenant=tenant, email=email, role="reviewer", source="atlan_jwt")
        repo.insert("principals", p)
    return CallerPrincipal(subject=p.id, email=p.email, role=p.role, tenant=p.tenant,
                           source="atlan_jwt")


def current_principal(request: Request, repo: Repository = Depends(get_repo),
                      settings: Settings = Depends(get_settings)) -> CallerPrincipal:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise _unauthorised("missing bearer token")
    token = auth[7:].strip()
    if settings.is_dev and settings.dev_token and hmac.compare_digest(token, settings.dev_token):
        return CallerPrincipal(subject="dev", email="dev@localhost", role="admin",
                               tenant=settings.default_tenant, source="dev")
    if token.startswith("t."):
        p = _bearer_principal(token, repo)
        if p is None:
            raise _unauthorised("unknown token")
        return p
    return _jwt_principal(token, repo, settings)


def require(role: str):
    def _dep(p: CallerPrincipal = Depends(current_principal)) -> CallerPrincipal:
        if not p.at_least(role):
            raise HTTPException(status_code=403, detail={"error": f"requires {role}", "code": "FORBIDDEN"})
        return p
    return _dep
