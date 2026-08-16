"""Tenant tokens: opaque bearer secrets, hashed at rest, slug-bound.

Token format: t.<slug>.<random>, 192 bits of entropy from secrets.token_urlsafe.
The DB stores sha256(token) and never the token itself; comparison goes through
hmac.compare_digest so it is constant-time. The slug is carried inside the token
and must equal the slug in the request path, checked before the hash is compared,
so a leaked cookie for one tenant is inert against another.

There is deliberately no keyed MAC here. An earlier version of this docstring
claimed "HMAC-checked slugs", which was false: hmac is used only for its
constant-time comparison helper. The security property holds without a key
because the token is a high-entropy random secret compared against a stored
hash; describing it as keyed would have been false assurance.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def make_slug(org: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", org.lower()).strip("-")[:24] or "org"
    if not base[0].isalnum():
        base = "org-" + base
    slug = base
    n = 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


def mint_token(slug: str) -> tuple[str, str]:
    """Returns (token, token_hash). Token is shown once and never stored."""
    token = f"t.{slug}.{secrets.token_urlsafe(24)}"
    return token, hashlib.sha256(token.encode()).hexdigest()


def token_slug(token: str) -> str | None:
    parts = token.split(".")
    if len(parts) == 3 and parts[0] == "t" and SLUG_RE.match(parts[1]):
        return parts[1]
    return None


def token_matches(token: str, stored_hash: str) -> bool:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return hmac.compare_digest(digest, stored_hash)
