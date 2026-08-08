"""Tenant-scoped evidence store.

Isolation is structural, not prompt-based: a store is constructed from exactly
one tenant directory and every chunk it emits carries that tenant tag. There is
no code path that loads two tenants into one store.

Contradiction detection is deterministic: sources declare machine-checkable
assertions in frontmatter (e.g. `assert.customer_data_deletion_days: 90`).
Two approved, in-force sources asserting different values for the same key
form a contradiction set — flagged before any model sees the question.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from pathlib import Path

from .models import Chunk, Source

FM_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _parse_date(s: str) -> date:
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def parse_source(path: Path, tenant: str) -> Source:
    raw = path.read_text(encoding="utf-8")
    m = FM_RE.match(raw)
    if not m:
        raise ValueError(f"{path.name}: missing frontmatter")
    meta: dict[str, str] = {}
    assertions: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip().strip('"')
        if k.startswith("assert."):
            assertions[k[len("assert."):]] = v
        else:
            meta[k] = v
    body = m.group(2).strip()
    return Source(
        source_id=meta["source_id"],
        tenant=tenant,
        title=meta["title"],
        type=meta["type"],
        version=meta["version"],
        effective_date=_parse_date(meta["effective_date"]),
        expiry_date=_parse_date(meta["expiry_date"]),
        owner=meta["owner"],
        approval_status=meta["approval_status"],
        topics=[t.strip().lower() for t in meta.get("topics", "").split(",") if t.strip()],
        assertions=assertions,
        body=body,
        sha256=hashlib.sha256(raw.encode()).hexdigest(),
    )


class EvidenceStore:
    def __init__(self, tenant: str, root: Path):
        self.tenant = tenant
        tenant_dir = root / tenant
        if not tenant_dir.is_dir():
            raise FileNotFoundError(f"no evidence directory for tenant '{tenant}'")
        self.sources: dict[str, Source] = {}
        for p in sorted(tenant_dir.glob("*.md")):
            s = parse_source(p, tenant)
            self.sources[s.source_id] = s

    # ---- chunks -----------------------------------------------------------
    def chunks(self) -> list[Chunk]:
        out: list[Chunk] = []
        for s in self.sources.values():
            paras = [p.strip() for p in s.body.split("\n\n") if p.strip()]
            for i, para in enumerate(paras, start=1):
                out.append(Chunk(source_id=s.source_id, tenant=s.tenant,
                                 location=f"para:{i}", text=para))
        return out

    # ---- integrity views --------------------------------------------------
    def stale_ids(self, today: date) -> set[str]:
        return {sid for sid, s in self.sources.items() if s.is_stale(today)}

    def contradictions(self, today: date) -> dict[str, list[Source]]:
        """assertion_key -> conflicting approved sources (>=2 distinct values)."""
        by_key: dict[str, list[Source]] = {}
        for s in self.sources.values():
            if not s.is_approved():
                continue
            for k in s.assertions:
                by_key.setdefault(k, []).append(s)
        out: dict[str, list[Source]] = {}
        for k, srcs in by_key.items():
            if len({s.assertions[k] for s in srcs}) > 1:
                out[k] = srcs
        return out

    def contradicted_source_ids(self, today: date) -> set[str]:
        ids: set[str] = set()
        for srcs in self.contradictions(today).values():
            ids |= {s.source_id for s in srcs}
        return ids
