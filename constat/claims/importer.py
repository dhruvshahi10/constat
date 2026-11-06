"""Seed the claim store from questionnaires already answered and sent.

Most teams start with a folder of completed questionnaires, not a claim
store. This turns one into reviewable work in two steps:

  preview  every answered row is screened, matched against existing claims
           and gated against them, then given an action:
             attach_answer  a verified claim covers it and the old answer
                            passes the gates: it becomes a reusable answer
             new_claim      nothing covers it: rows that ask the same thing
                            are clustered and one draft claim is proposed
             skip           too short to be a fact ("Yes"), suspicious, or
                            in conflict with a claim (the reason names it)
  commit   a person confirms the actions. Draft claims are opened as
           proposals that a second person approves; attached answers are
           re-gated server-side first. Nothing in the client's copy of the
           rows is trusted except the chosen action.

Old answers are evidence of what was said, not proof of what is true. That
is why nothing here creates a verified claim.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from ..intake.parsers import RawQuestion
from ..intake.quarantine import screen_raw
from .gates import RELEVANCE_MIN, canon, gate
from .match import ClaimMatcher, jaccard, key_terms
from .models import ApprovedAnswer, Audience, Claim, ClaimStatus, EvidenceRef
from .store import ClaimStore

CLUSTER_JACCARD = 0.5
MIN_FACT_WORDS = 4
IMPORT_VALIDITY_DAYS = 180          # an imported, unverified fact is reviewed within six months
_LEAD = re.compile(r"^\s*(yes|no|n/?a|correct|confirmed|affirmative)\s*[.,:;!-]*\s*", re.I)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9-]+")


@dataclass
class ImportRow:
    ordinal: int
    question: str
    answer: str
    domain: str
    cluster: str
    confidence: float
    existing_claim_id: Optional[str]
    action: str                       # new_claim | attach_answer | skip
    suggested_owner: Optional[str]
    reason: str


@dataclass
class ImportPreview:
    id: str
    filename: str
    customer: str
    audience: str
    created_on: str
    actor: str
    rows: list[ImportRow] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)      # people who own claims today, for the owner picker

    @property
    def counts(self) -> dict[str, int]:
        c = {"new_claim": 0, "attach_answer": 0, "skip": 0}
        for r in self.rows:
            c[r.action] += 1
        return c

    def to_dict(self) -> dict:
        return {"id": self.id, "filename": self.filename, "customer": self.customer, "audience": self.audience,
                "created_on": self.created_on, "actor": self.actor,
                "rows": [asdict(r) for r in self.rows], "counts": self.counts, "owners": self.owners,
                "proposals_expected": len({r.cluster for r in self.rows if r.action == "new_claim"})}

    @classmethod
    def from_dict(cls, d: dict) -> "ImportPreview":
        return cls(id=d["id"], filename=d["filename"], customer=d["customer"], audience=d["audience"],
                   created_on=d["created_on"], actor=d["actor"], rows=[ImportRow(**r) for r in d["rows"]],
                   owners=list(d.get("owners", [])))


@dataclass
class CommitResult:
    proposals: int = 0
    attached: int = 0
    skipped: int = 0
    proposal_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def fact_text(answer: str) -> str:
    """The factual part of an answer: drop a leading Yes/No, keep the rest."""
    return _LEAD.sub("", canon(answer)).strip()


def _fact_words(text: str) -> int:
    return len(_WORD.findall(text or ""))


def _cluster_id(terms: set[str]) -> str:
    return "c-" + hashlib.sha256(" ".join(sorted(terms)).encode()).hexdigest()[:8]


def preview(rows: list[RawQuestion], store: ClaimStore, *, filename: str, customer: str,
            audience: Audience, actor: str, today: date, domain_owners: dict[str, str] | None = None) -> ImportPreview:
    matcher = ClaimMatcher(store)
    pid = hashlib.sha256(f"{filename}|{customer}|{actor}|{today}|{len(rows)}|{rows[0].text if rows else ''}"
                         .encode()).hexdigest()[:12]
    prev = ImportPreview(id=pid, filename=filename, customer=customer, audience=audience.value,
                         created_on=today.isoformat(), actor=actor,
                         owners=sorted({c.owner for c in store.list() if "@" in c.owner}))
    clusters: list[tuple[str, set[str]]] = []
    owners = {k.lower(): v for k, v in (domain_owners or {}).items()}

    for r in rows:
        q, a = r.text, r.answer
        owner_guess = owners.get((r.domain or "").lower())
        base = dict(ordinal=r.ordinal, question=q, answer=a, domain=r.domain, existing_claim_id=None,
                    suggested_owner=owner_guess)
        if not a.strip():
            continue                                   # unanswered rows are not part of an import
        screen = screen_raw(q + "\n" + a)
        if screen.quarantined:
            prev.rows.append(ImportRow(**base, cluster="", confidence=0.0, action="skip",
                                       reason="screened: " + "; ".join(screen.reasons)[:200]))
            continue
        fact = fact_text(a)
        if _fact_words(fact) < MIN_FACT_WORDS:
            prev.rows.append(ImportRow(**base, cluster="", confidence=0.0, action="skip",
                                       reason="answer is too short to state a fact; a claim needs the fact, not 'Yes'"))
            continue

        matches = matcher.match(q, today, audience)
        top = matches[0] if matches else None
        if top and top.coverage >= RELEVANCE_MIN:
            v = gate(q, matches, today, audience, candidate_answer=fact, domain=r.domain)
            if v.outcome == "ANSWER" and v.claim_id:
                prev.rows.append(ImportRow(**{**base, "existing_claim_id": v.claim_id,
                                              "suggested_owner": top.claim.owner},
                                           cluster=v.claim_id, confidence=round(top.coverage, 2),
                                           action="attach_answer",
                                           reason=f"{v.claim_id} covers it and the old answer passes the gates"))
                continue
            if top.claim.status == ClaimStatus.VERIFIED and v.flags:
                prev.rows.append(ImportRow(**{**base, "existing_claim_id": top.claim.claim_id,
                                              "suggested_owner": top.claim.owner},
                                           cluster=top.claim.claim_id, confidence=round(top.coverage, 2),
                                           action="skip",
                                           reason=f"conflicts with {top.claim.claim_id}: {', '.join(v.flags)}. "
                                                  f"What was sent before differs from the claim; ask {top.claim.owner}"))
                continue

        terms = key_terms(q)
        cid, best = None, 0.0
        for existing_id, existing_terms in clusters:
            j = jaccard(terms, existing_terms)
            if j >= CLUSTER_JACCARD and j > best:
                cid, best = existing_id, j
        if cid is None:
            cid, best = _cluster_id(terms), 1.0
            clusters.append((cid, terms))
        prev.rows.append(ImportRow(**base, cluster=cid, confidence=round(best, 2), action="new_claim",
                                   reason="no claim covers this; it becomes a draft claim for its owner to approve"))
    return prev


def _slug(text: str) -> str:
    words = [w.lower() for w in _WORD.findall(text)][:4]
    return "-".join(words)[:40] or "claim"


def commit(prev: ImportPreview, chosen: dict[int, str], store: ClaimStore, *, actor: str, today: date,
           owners: dict[int, str] | None = None) -> CommitResult:
    """`chosen` maps ordinal to action and `owners` ordinal to the owner a
    person picked. Only those come from the client; the question, answer and
    claim come from the stored preview. An owner must be a person's address;
    the store's hygiene rules refuse team aliases."""
    owners = owners or {}
    res = CommitResult()
    audience = Audience(prev.audience)
    matcher = ClaimMatcher(store)
    by_cluster: dict[str, list[ImportRow]] = {}
    for row in prev.rows:
        action = chosen.get(row.ordinal, row.action)
        if action not in ("new_claim", "attach_answer", "skip"):
            action = "skip"
        if action == "attach_answer" and not row.existing_claim_id:
            action = "skip"
            res.notes.append(f"row {row.ordinal}: no existing claim to attach to")
        if action == "skip":
            res.skipped += 1
            continue
        # the screens run again on every committed row, whatever action was chosen
        screen = screen_raw(row.question + "\n" + row.answer)
        if screen.quarantined or _fact_words(fact_text(row.answer)) < MIN_FACT_WORDS:
            res.skipped += 1
            res.notes.append(f"row {row.ordinal}: refused at commit ({'; '.join(screen.reasons) or 'too short to be a fact'})")
            continue
        if action == "attach_answer":
            fact = fact_text(row.answer)
            matches = matcher.match(row.question, today, audience)
            v = gate(row.question, matches, today, audience, candidate_answer=fact, domain=row.domain)
            if v.outcome != "ANSWER" or v.claim_id != row.existing_claim_id or not hasattr(store, "add_approved_answer"):
                res.skipped += 1
                res.notes.append(f"row {row.ordinal}: re-gated as {v.outcome} {v.flags}; not attached")
                continue
            store.add_approved_answer(row.existing_claim_id, ApprovedAnswer(
                question=row.question, answer=fact, approver=actor, approved_on=today, audience=audience),
                approver=actor, today=today)
            res.attached += 1
            continue
        by_cluster.setdefault(row.cluster or f"row-{row.ordinal}", []).append(row)

    for cluster, members in by_cluster.items():
        lead = members[0]
        statement = fact_text(lead.answer)
        picked = next((owners[m.ordinal] for m in members if owners.get(m.ordinal)), None)
        owner = picked or (lead.suggested_owner if lead.suggested_owner and "@" in lead.suggested_owner else actor)
        claim_id = f"import.{_slug(lead.domain or lead.question)}.{cluster[-6:]}"
        keywords = sorted(set().union(*(key_terms(m.question) for m in members)))[:40]
        claim = Claim(
            claim_id=claim_id, statement=statement, owner=owner,
            scope=f"As answered to {prev.customer} ({prev.filename}); confirm the scope before approving",
            valid_from=today, valid_until=today + timedelta(days=IMPORT_VALIDITY_DAYS),
            evidence_refs=[EvidenceRef("statement", f"import:{prev.filename}#rows "
                                       + ",".join(str(m.ordinal) for m in members))],
            exceptions=[], audience=audience, status=ClaimStatus.DRAFT, keywords=keywords,
            topics=[lead.domain.lower()] if lead.domain else [],
            approved_answers=[ApprovedAnswer(question=m.question, answer=fact_text(m.answer), approver=actor,
                                             approved_on=today, audience=audience) for m in members],
            notes=(f"Imported from a sent questionnaire by {actor} on {today.isoformat()}. "
                   f"An old answer is evidence of what was said, not proof it is true: add evidence refs and "
                   f"exceptions before approving."))
        try:
            p = store.propose(claim, actor=actor, reason=f"import from {prev.filename}", today=today)
            res.proposals += 1
            res.proposal_ids.append(p.proposal_id)
        except ValueError as e:
            res.skipped += len(members)
            res.notes.append(f"cluster {cluster}: {e}")
    return res


class PreviewStore:
    """Previews persisted beside the claim store, so a commit survives a restart."""

    def __init__(self, root: Path):
        self.root = Path(root) / "imports"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, pid: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", pid or ""):
            raise KeyError(pid)
        return self.root / f"{pid}.json"

    def save(self, prev: ImportPreview) -> None:
        self._path(prev.id).write_text(json.dumps(prev.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")

    def load(self, pid: str) -> ImportPreview:
        p = self._path(pid)
        if not p.exists():
            raise KeyError(pid)
        return ImportPreview.from_dict(json.loads(p.read_text(encoding="utf-8")))
