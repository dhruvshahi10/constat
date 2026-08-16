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
        d["risk"] = self.risk.value
        return d

    @classmethod
    def from_contract(cls, d: dict) -> "Draft":
        """Inverse of to_contract(): rehydrate a Draft from contracts.json."""
        data = dict(d)
        data["citations"] = [Citation(**c) for c in data.get("citations", [])]
        data["evidence_coverage"] = Coverage(data["evidence_coverage"])
        data["risk"] = Risk(data["risk"])
        return cls(**data)


@dataclass
class Approval:
    question_id: str
    actor: str
    action: str               # approved | edited | rejected
    timestamp: str
    note: str = ""
