"""Server configuration from environment. Everything has a local-dev default."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

DATA = Path(os.environ.get("TRUSTOPS_DATA", "./data-hosted")).resolve()
DB_PATH = DATA / "trustops.db"
TENANTS = DATA / "tenants"

# HMAC key for tenant tokens. Render injects TRUSTOPS_SECRET (generateValue);
# a missing value gets a per-boot random key, which invalidates tokens on
# restart — fine for dev, unacceptable in prod, so warn loudly.
SECRET = os.environ.get("TRUSTOPS_SECRET", "")
EPHEMERAL_SECRET = not SECRET
if EPHEMERAL_SECRET:
    SECRET = secrets.token_hex(32)

PORT = int(os.environ.get("PORT", "8790"))
HOST = os.environ.get("TRUSTOPS_HOST", "127.0.0.1")

# limits
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_BODY_BYTES = 6 * 1024 * 1024
MAX_DOCS_PER_TENANT = 20
MAX_EXTRACT_CHARS = 200_000
RUN_QUOTA = 3
SIGNUPS_PER_IP_PER_DAY = 3
GLOBAL_QUEUE_DEPTH = 32
TENANT_TTL_DAYS = 14

HOSTED_DRAFTER = os.environ.get("TRUSTOPS_DRAFTER", "gemini")


def tenant_dir(slug: str) -> Path:
    return TENANTS / slug


def evidence_root(slug: str) -> Path:
    # EvidenceStore joins root/<tenant>; rooting at the tenant's own tree means
    # even a wrong tenant argument cannot escape into a sibling's data
    return tenant_dir(slug) / "evidence"


def runs_dir(slug: str) -> Path:
    return tenant_dir(slug) / "runs"


def uploads_dir(slug: str) -> Path:
    return tenant_dir(slug) / "uploads"
