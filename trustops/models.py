"""TrustOps core data model.

Mirrors the venture blueprint's minimum data model:
  source, question, draft (answer contract), approval, audit_event.

The Draft is the machine-readable answer contract:
  {question_id, answer, citations[], evidence_coverage, risk, gaps[], requires_human}
Confidence never overrides missing evidence — coverage is derived from
citations that survived the deterministic gates, not from model self-report.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from enum import Enum
from typing import Optional


class Coverage(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NONE = "none"


class Risk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AnswerStatus(str, Enum):
    """What is true about the evidence behind an answer.

    Deliberately not a confidence score. A score invites someone to ship a 0.72;
    a status names the state of the evidence and is derived in code from
    citations that survived the gates, never from the drafter's self-report.
    """
    EVIDENCE_BACKED = "evidence_backed"   # cited, gate-clean, no gaps, ready to ship
    PARTIAL = "partial"                   # cited, but gaps recorded against it
    REQUIRES_HUMAN = "requires_human"     # cited and clean, but a person must sign it
    NO_EVIDENCE = "no_evidence"           # refused: nothing approved supports an answer
    ROUTED = "routed"                     # removed from automation before drafting
    HUMAN_AUTHORED = "human_authored"     # a named person wrote this; not derived from evidence

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").upper()

    @property
    def released(self) -> bool:
        """Whether an answer left the system at all."""
        return self in (AnswerStatus.EVIDENCE_BACKED, AnswerStatus.PARTIAL,
                        AnswerStatus.REQUIRES_HUMAN, AnswerStatus.HUMAN_AUTHORED)


class QState(str, Enum):
    RECEIVED = "RECEIVED"
    CLASSIFIED = "CLASSIFIED"
    DRAFTED = "DRAFTED"
    EXCEPTION = "EXCEPTION"
    GRC_REVIEW = "GRC_REVIEW"
    DELIVERED = "DELIVERED"


@dataclass
class Source:
    source_id: str
    tenant: str
    title: str
    type: str                 # policy | standard | plan | report | attestation | certificate | roadmap | register
    version: str
    effective_date: date
    expiry_date: date
    owner: str
    approval_status: str      # approved | draft | rejected
    topics: list[str]
    assertions: dict[str, str]  # machine-checkable claims, e.g. customer_data_deletion_days
    body: str
    sha256: str

    def is_stale(self, today: date) -> bool:
        return today > self.expiry_date

    def is_approved(self) -> bool:
        return self.approval_status == "approved"


@dataclass
class Chunk:
    source_id: str
    tenant: str
    location: str             # e.g. "para:3"
    text: str


@dataclass
class Citation:
    source_id: str
    version: str
    location: str
    excerpt: str


@dataclass
class Question:
    question_id: str
    row: int                  # original spreadsheet row — identity is preserved end to end
    domain: str
    text: str
    theme: str = ""
    risk_level: Risk = Risk.MEDIUM
    state: QState = QState.RECEIVED


@dataclass
class Draft:
    question_id: str
    answer: Optional[str]
    citations: list[Citation] = field(default_factory=list)
    evidence_coverage: Coverage = Coverage.NONE
    status: AnswerStatus = AnswerStatus.NO_EVIDENCE
    risk: Risk = Risk.MEDIUM
    gaps: list[str] = field(default_factory=list)
    requires_human: bool = True
    abstained: bool = False
    route: Optional[str] = None      # e.g. "SME", "LEGAL", "SOURCE_OWNER:<email>"
    gate_flags: list[str] = field(default_factory=list)
    drafter: str = "unset"
    model_version: str = "n/a"
    prompt_version: str = "n/a"

    def to_contract(self) -> dict:
        d = asdict(self)
        d["evidence_coverage"] = self.evidence_coverage.value
        d["status"] = self.status.value
        d["risk"] = self.risk.value
        return d

    @classmethod
    def from_contract(cls, data: dict) -> "Draft":
        """Rehydrate a draft from a persisted contract — used by the review
        session, which reopens a completed run to record human decisions."""
        return cls(
            question_id=data["question_id"],
            answer=data.get("answer"),
            citations=[Citation(**c) for c in data.get("citations", [])],
            evidence_coverage=Coverage(data.get("evidence_coverage", "none")),
            status=AnswerStatus(data.get("status", "no_evidence")),
            risk=Risk(data.get("risk", "medium")),
            gaps=list(data.get("gaps", [])),
            requires_human=bool(data.get("requires_human", True)),
            abstained=bool(data.get("abstained", False)),
            route=data.get("route"),
            gate_flags=list(data.get("gate_flags", [])),
            drafter=data.get("drafter", "unset"),
            model_version=data.get("model_version", "n/a"),
            prompt_version=data.get("prompt_version", "n/a"),
        )


@dataclass
class Approval:
    question_id: str
    actor: str
    action: str               # approved | edited | rejected
    timestamp: str
    note: str = ""
