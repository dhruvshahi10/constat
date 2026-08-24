"""Client workspaces.

A tenant is a directory under the evidence root. That is deliberate: isolation
is a property of the filesystem layout and of `EvidenceStore`'s single-tenant
construction, not of a `WHERE tenant_id = ?` that somebody can forget to write.

`tenant.json` adds the operator-facing metadata a directory cannot carry —
display name, corpus owner, trust-page configuration. It is optional: a tenant
directory with no config still works, and defaults are derived from the slug,
so an existing corpus never breaks by not having been configured.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

CONFIG_NAME = "tenant.json"
RESERVED = {"_staging"}
SLUG_PAT = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}$")


@dataclass
class TrustPageConfig:
    enabled: bool = True
    headline: str = ""
    contact_email: str = ""
    intro: str = ""


@dataclass
class Tenant:
    slug: str
    display_name: str
    owner: str = ""
    created: str = ""
    trust_page: TrustPageConfig = field(default_factory=TrustPageConfig)

    @property
    def title(self) -> str:
        return self.display_name or self.slug

    def to_dict(self) -> dict:
        return asdict(self)


def _tenant_dir(evidence_root: Path, slug: str) -> Path:
    return Path(evidence_root) / slug


def _default_display(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def load_tenant(evidence_root: Path, slug: str) -> Tenant:
    """Config for one tenant, synthesising defaults when none was written."""
    directory = _tenant_dir(evidence_root, slug)
    if not directory.is_dir():
        raise FileNotFoundError(f"no workspace for tenant '{slug}'")
    config = directory / CONFIG_NAME
    if not config.is_file():
        return Tenant(slug=slug, display_name=_default_display(slug))
    raw = json.loads(config.read_text(encoding="utf-8"))
    trust = raw.get("trust_page") or {}
    return Tenant(
        slug=slug,
        display_name=raw.get("display_name") or _default_display(slug),
        owner=raw.get("owner", ""),
        created=raw.get("created", ""),
        trust_page=TrustPageConfig(
            enabled=bool(trust.get("enabled", True)),
            headline=trust.get("headline", ""),
            contact_email=trust.get("contact_email", ""),
            intro=trust.get("intro", ""),
        ),
    )


def list_tenants(evidence_root: Path) -> list[Tenant]:
    root = Path(evidence_root)
    if not root.is_dir():
        return []
    slugs = sorted(d.name for d in root.iterdir()
                   if d.is_dir() and d.name not in RESERVED and not d.name.startswith("."))
    return [load_tenant(root, slug) for slug in slugs]


def source_count(evidence_root: Path, slug: str) -> int:
    return len(list(_tenant_dir(evidence_root, slug).glob("*.md")))


def staged_count(evidence_root: Path, slug: str) -> int:
    """Sources awaiting human approval. REVIEW.md is the queue's cover sheet,
    not a source, so it is not counted."""
    staging = _tenant_dir(evidence_root, slug) / "_staging"
    if not staging.is_dir():
        return 0
    return len([p for p in staging.glob("*.md") if p.name != "REVIEW.md"])


def create_tenant(evidence_root: Path, slug: str, display_name: str = "",
                  owner: str = "", contact_email: str = "",
                  headline: str = "", intro: str = "") -> Tenant:
    if not SLUG_PAT.match(slug):
        raise ValueError(
            f"invalid tenant slug '{slug}': use lowercase letters, digits and hyphens "
            f"(2-49 chars). The slug is a directory name and a retrieval boundary.")
    if slug in RESERVED:
        raise ValueError(f"'{slug}' is reserved")
    directory = _tenant_dir(evidence_root, slug)
    if (directory / CONFIG_NAME).is_file():
        raise FileExistsError(f"tenant '{slug}' already configured")
    directory.mkdir(parents=True, exist_ok=True)
    tenant = Tenant(
        slug=slug,
        display_name=display_name or _default_display(slug),
        owner=owner,
        created=date.today().isoformat(),
        trust_page=TrustPageConfig(headline=headline, contact_email=contact_email, intro=intro),
    )
    (directory / CONFIG_NAME).write_text(
        json.dumps(tenant.to_dict(), indent=2) + "\n", encoding="utf-8")
    return tenant
