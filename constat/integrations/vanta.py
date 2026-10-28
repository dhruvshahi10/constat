"""Vanta as the evidence spine.

A claim points at a Vanta test by an evidence ref of kind `vanta_test` and
ref `vanta:test:<test id>`. A sync takes the latest test results and:
  * a failing test proposes the claim stale (valid_until = yesterday) and
    opens a decision for the owner with a deadline. It never deprecates the
    claim and never unpublishes anything: one failing host does not falsify
    "we encrypt at rest". A person decides.
  * a passing test records the check date on the evidence ref.
  * a muted or missing test is a finding of its own, reported, not hidden.

The Vanta API client is deliberately thin and tolerant: the exact response
shape of GET /v1/tests is not pinned here (UNVERIFIED against the live API);
`parse_tests` accepts the common shapes and the sync works on the normalised
TestResult list, which tests can construct directly.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

from ..claims import Claim, ClaimStore
from ..claims.models import EvidenceRef

VANTA_API = "https://api.vanta.com/v1/tests"
SYNC_ACTOR = "vanta-sync"
DECISION_DAYS = 7


@dataclass
class TestResult:
    test_id: str
    status: str                 # passing | failing | muted | not_applicable | unknown
    checked_on: Optional[date] = None
    name: str = ""


@dataclass
class Decision:
    claim_id: str
    owner: str
    test_id: str
    status: str
    deadline: date
    proposal_id: Optional[str] = None
    note: str = ""


@dataclass
class SyncReport:
    checked: int = 0
    stale_proposed: list[Decision] = field(default_factory=list)
    muted: list[Decision] = field(default_factory=list)
    missing: list[Decision] = field(default_factory=list)
    touched: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"checked": self.checked,
                "stale_proposed": [d.__dict__ | {"deadline": d.deadline.isoformat()} for d in self.stale_proposed],
                "muted": [d.__dict__ | {"deadline": d.deadline.isoformat()} for d in self.muted],
                "missing": [d.__dict__ | {"deadline": d.deadline.isoformat()} for d in self.missing],
                "touched": self.touched}


def test_id_of(ref: EvidenceRef) -> Optional[str]:
    if ref.kind != "vanta_test":
        return None
    r = ref.ref
    return r[len("vanta:test:"):] if r.startswith("vanta:test:") else r


def parse_tests(payload) -> list[TestResult]:
    """Normalise a Vanta tests response. Accepts {"results": {"data": [...]}},
    {"data": [...]} or a bare list; each entry with id/testId, status/outcome,
    and an optional latestFlipTime or lastRun date."""
    if isinstance(payload, dict):
        data = payload.get("results", payload).get("data", payload.get("data", [])) \
            if isinstance(payload.get("results", payload), dict) else payload.get("data", [])
    else:
        data = payload
    out = []
    for e in data or []:
        if not isinstance(e, dict):
            continue
        tid = str(e.get("testId") or e.get("id") or e.get("test_id") or "")
        raw = str(e.get("status") or e.get("outcome") or "unknown").lower()
        status = {"pass": "passing", "passed": "passing", "ok": "passing", "fail": "failing",
                  "failed": "failing", "needs_attention": "failing", "deactivated": "muted",
                  "disabled": "muted", "na": "not_applicable"}.get(raw, raw)
        when = e.get("latestFlipTime") or e.get("lastRun") or e.get("checked_on")
        checked = None
        if isinstance(when, str) and len(when) >= 10:
            try:
                checked = date.fromisoformat(when[:10])
            except ValueError:
                checked = None
        if tid:
            out.append(TestResult(test_id=tid, status=status, checked_on=checked, name=str(e.get("name") or "")))
    return out


def fetch_tests(token: str, timeout: float = 30.0) -> list[TestResult]:
    req = urllib.request.Request(VANTA_API, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse_tests(json.loads(r.read().decode()))


def sync(store: ClaimStore, results: Iterable[TestResult], today: date, actor: str = SYNC_ACTOR) -> SyncReport:
    by_id = {r.test_id: r for r in results}
    rep = SyncReport()
    already_open = {p.claim.claim_id for p in store.pending() if p.actor == actor}
    for c in store.list():
        for ref in c.evidence_refs:
            tid = test_id_of(ref)
            if not tid:
                continue
            rep.checked += 1
            res = by_id.get(tid)
            deadline = today + timedelta(days=DECISION_DAYS)
            if res is None:
                rep.missing.append(Decision(c.claim_id, c.owner, tid, "missing", deadline,
                                            note="the claim cites a Vanta test that no longer exists"))
                continue
            if res.status == "muted":
                rep.muted.append(Decision(c.claim_id, c.owner, tid, "muted", deadline,
                                          note="muted tests are findings: the check is not running"))
                continue
            if res.status == "failing":
                if c.valid_until < today or c.claim_id in already_open:
                    continue  # already stale, or the decision is already open
                updated = Claim.from_dict(c.to_dict())
                updated.valid_until = today - timedelta(days=1)
                updated.notes = (c.notes + "\n" if c.notes else "") + \
                    f"{today.isoformat()}: Vanta test {tid} is failing; claim marked stale pending a decision by " \
                    f"{c.owner} before {deadline.isoformat()}. Not deprecated, not unpublished."
                try:
                    prop = store.propose(updated, actor=actor, reason=f"Vanta test {tid} failing", today=today)
                    pid = prop.proposal_id
                except ValueError:
                    pid = None
                rep.stale_proposed.append(Decision(c.claim_id, c.owner, tid, "failing", deadline, pid,
                                                   note="failing test; decision opened, claim not unpublished"))
                continue
            if res.status == "passing" and hasattr(store, "record_evidence_check"):
                store.record_evidence_check(c.claim_id, ref.ref, res.checked_on or today)
                rep.touched.append(f"{c.claim_id}:{tid}")
    return rep
