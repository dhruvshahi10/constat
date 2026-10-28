"""Claim data model.

A claim is the unit of truth a questionnaire answer may rest on. It is
deliberately small: one statement, one accountable human, evidence it points
at, the scope it covers, the exceptions that must travel with it, who may see
it, when it stops being true, and a version an answer can cite.

Design rules this model enforces in code rather than in prose:
  * exceptions are a list, never free text inside the statement, so a gate
    can check that each one appears in the answer (the telemetry trap)
  * audience is ordered; a claim never flows to a wider audience than its own
  * status and validity are separate: a verified claim can still be expired
  * version_hash() is content-addressed, so a sent answer can record exactly
    what it rested on even when the backing store mutates in place (Atlan
    glossary terms have no immutable versions)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import date
from enum import Enum
from typing import Optional


class ClaimStatus(str, Enum):
    DRAFT = "draft"            # proposed, not yet approved by a human
    VERIFIED = "verified"      # approved; may support an answer
    DEPRECATED = "deprecated"  # retired; must never support an answer


class Audience(str, Enum):
    PUBLIC = "public"
    NDA = "nda"
    INTERNAL = "internal"

    @property
    def rank(self) -> int:
        return {"public": 0, "nda": 1, "internal": 2}[self.value]

    def may_receive(self, claim_audience: "Audience") -> bool:
        """A request made at this audience may use a claim of that audience
        only if the claim is at least as widely shareable."""
        return claim_audience.rank <= self.rank


class DifficultyClass(str, Enum):
    """Measured per question, never in total: an overall automation rate hides
    the hard questions piling up."""
    REUSED = "reused"                      # a previously approved answer fits verbatim
    COVERED = "covered"                    # a verified claim covers it; drafting needed
    PARAMETER_MISSING = "parameter_missing"  # claim found, the asked-for value is absent
    NOVEL = "novel"                        # no covering claim; routes to an owner
    CONTRACTUAL = "contractual"            # SLA, guarantee or legal wording; a human decides


EVIDENCE_KINDS = {"vanta_test", "policy", "standard", "report", "certificate",
                  "attestation", "config", "statement"}
# evidence classes that may support a certification or attestation claim
CERT_EVIDENCE_KINDS = {"certificate", "attestation"}


@dataclass(frozen=True)
class EvidenceRef:
    kind: str                  # one of EVIDENCE_KINDS
    ref: str                   # e.g. "vanta:test:aws-s3-encryption", "POL-ENC-001 v2.1"
    checked_on: Optional[date] = None

    def __post_init__(self):
        if self.kind not in EVIDENCE_KINDS:
            raise ValueError(f"unknown evidence kind {self.kind!r}")


@dataclass
class ApprovedAnswer:
    """An answer a human approved for a question that rested on this claim.
    The reuse corpus: a new question that matches closely enough is answered
    with this text, verbatim, and classed REUSED."""
    question: str
    answer: str
    approver: str
    approved_on: date
    audience: Audience = Audience.NDA
    claim_version_hash: str = ""


@dataclass
class Claim:
    claim_id: str
    statement: str
    owner: str                               # a person, accountable; never a team alias
    scope: str                               # what the statement covers
    valid_from: date
    valid_until: date
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)   # must travel with any answer
    audience: Audience = Audience.NDA
    framework_map: list[str] = field(default_factory=list)  # "SOC2:CC6.1", "ISO27001:A.8.24"
    status: ClaimStatus = ClaimStatus.DRAFT
    version: int = 1
    keywords: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    approved_answers: list[ApprovedAnswer] = field(default_factory=list)
    updated_by: str = ""
    updated_on: Optional[date] = None
    notes: str = ""

    # ---- state ----------------------------------------------------------
    def is_fresh(self, today: date) -> bool:
        return self.valid_from <= today <= self.valid_until

    def is_usable(self, today: date, request_audience: Audience) -> tuple[bool, str]:
        """Whether this claim may support an answer right now, and why not."""
        if self.status == ClaimStatus.DEPRECATED:
            return False, "DEPRECATED"
        if self.status == ClaimStatus.DRAFT:
            return False, "DRAFT"
        if not self.is_fresh(today):
            return False, "STALE"
        if not request_audience.may_receive(self.audience):
            return False, "AUDIENCE"
        return True, ""

    def has_cert_evidence(self) -> bool:
        return any(e.kind in CERT_EVIDENCE_KINDS for e in self.evidence_refs)

    # ---- identity -------------------------------------------------------
    def content_fields(self) -> dict:
        """The fields whose change makes this a materially different claim."""
        return {
            "claim_id": self.claim_id,
            "statement": self.statement,
            "scope": self.scope,
            "exceptions": list(self.exceptions),
            "audience": self.audience.value,
            "evidence_refs": [[e.kind, e.ref] for e in self.evidence_refs],
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            "status": self.status.value,
        }

    def version_hash(self) -> str:
        payload = json.dumps(self.content_fields(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    # ---- serialisation --------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["audience"] = self.audience.value
        d["status"] = self.status.value
        d["valid_from"] = self.valid_from.isoformat()
        d["valid_until"] = self.valid_until.isoformat()
        d["updated_on"] = self.updated_on.isoformat() if self.updated_on else None
        d["evidence_refs"] = [
            {"kind": e.kind, "ref": e.ref,
             "checked_on": e.checked_on.isoformat() if e.checked_on else None}
            for e in self.evidence_refs]
        d["approved_answers"] = [
            {**asdict(a), "approved_on": a.approved_on.isoformat(),
             "audience": a.audience.value}
            for a in self.approved_answers]
        d["version_hash"] = self.version_hash()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Claim":
        d = dict(d)
        d.pop("version_hash", None)
        d["audience"] = Audience(d.get("audience", "nda"))
        d["status"] = ClaimStatus(d.get("status", "draft"))
        d["valid_from"] = _d(d["valid_from"])
        d["valid_until"] = _d(d["valid_until"])
        d["updated_on"] = _d(d["updated_on"]) if d.get("updated_on") else None
        d["evidence_refs"] = [
            EvidenceRef(e["kind"], e["ref"], _d(e["checked_on"]) if e.get("checked_on") else None)
            for e in d.get("evidence_refs", [])]
        d["approved_answers"] = [
            ApprovedAnswer(question=a["question"], answer=a["answer"], approver=a["approver"],
                           approved_on=_d(a["approved_on"]),
                           audience=Audience(a.get("audience", "nda")),
                           claim_version_hash=a.get("claim_version_hash", ""))
            for a in d.get("approved_answers", [])]
        return cls(**d)

    def validate(self) -> list[str]:
        """Hygiene problems a store refuses to approve. Learned from watching
        knowledge bases decay: departed owners still listed, blank scope."""
        problems = []
        if not self.statement.strip():
            problems.append("statement is empty")
        if "@" not in self.owner or self.owner.split("@")[0] in {"security", "grc", "team", "it", "ops"}:
            problems.append(f"owner {self.owner!r} must be a person's address, not a team alias")
        if not self.scope.strip():
            problems.append("scope is empty")
        if self.valid_until < self.valid_from:
            problems.append("valid_until is before valid_from")
        if self.status == ClaimStatus.VERIFIED and not self.evidence_refs:
            problems.append("a verified claim needs at least one evidence reference")
        return problems


@dataclass
class Proposal:
    """A write that has not happened yet. Mirrors the Atlan MCP contract:
    write tools return a preview and wait for approval before writing."""
    proposal_id: str
    claim: Claim
    actor: str
    reason: str
    created_on: date
    status: str = "pending"      # pending | approved | rejected
    decided_by: str = ""
    decided_on: Optional[date] = None
    previous_version_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id, "claim": self.claim.to_dict(),
            "actor": self.actor, "reason": self.reason,
            "created_on": self.created_on.isoformat(), "status": self.status,
            "decided_by": self.decided_by,
            "decided_on": self.decided_on.isoformat() if self.decided_on else None,
            "previous_version_hash": self.previous_version_hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Proposal":
        return cls(proposal_id=d["proposal_id"], claim=Claim.from_dict(d["claim"]),
                   actor=d["actor"], reason=d["reason"], created_on=_d(d["created_on"]),
                   status=d.get("status", "pending"), decided_by=d.get("decided_by", ""),
                   decided_on=_d(d["decided_on"]) if d.get("decided_on") else None,
                   previous_version_hash=d.get("previous_version_hash", ""))


def _d(s: str) -> date:
    return date.fromisoformat(s)
