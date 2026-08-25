"""Server configuration from environment. Everything has a local-dev default."""
from __future__ import annotations

import os
from pathlib import Path

DATA = Path(os.environ.get("CONSTAT_DATA", "./data-hosted")).resolve()
DB_PATH = DATA / "constat.db"
TENANTS = DATA / "tenants"

# No server-side secret is needed for auth: mint_token() draws its randomness
# from secrets.token_urlsafe and only sha256(token) is persisted, in SQLite on
# a durable disk. Tokens therefore survive restarts and there is nothing to
# rotate. (render.yaml still declares CONSTAT_SECRET; it is unused and can be
# dropped there whenever that file is next touched.)

PORT = int(os.environ.get("PORT", "8790"))
HOST = os.environ.get("CONSTAT_HOST", "127.0.0.1")

# limits
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_BODY_BYTES = 6 * 1024 * 1024
MAX_DOCS_PER_TENANT = 20
MAX_TENANT_BYTES = 60 * 1024 * 1024      # raw blobs kept per workspace
MAX_EXTRACT_CHARS = 200_000
RUN_QUOTA = 3
SIGNUPS_PER_IP_PER_DAY = 3
SIGNUPS_PER_DAY_GLOBAL = int(os.environ.get("CONSTAT_SIGNUPS_PER_DAY", "200"))
GLOBAL_QUEUE_DEPTH = 32
TENANT_TTL_DAYS = 14
KEEP_RUN_DIRS = 5                        # newest N run output dirs per tenant

# HTTP hardening
SOCKET_TIMEOUT_S = 30                    # slowloris ceiling per connection
MAX_CONNECTIONS = int(os.environ.get("CONSTAT_MAX_CONNECTIONS", "64"))

# A run holding the single worker forever starves every other tenant.
RUN_BUDGET_S = int(os.environ.get("CONSTAT_RUN_BUDGET_S", "420"))
# Grace we give an over-budget run to notice it lost and stop, before the
# worker starts the next job alongside it.
ORPHAN_GRACE_S = int(os.environ.get("CONSTAT_ORPHAN_GRACE_S", "30"))

HOSTED_DRAFTER = os.environ.get("CONSTAT_DRAFTER", "gemini")


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
