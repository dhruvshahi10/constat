"""Computed confidence for an answer that passed every gate.

The gates decide whether an answer may be shown; confidence says how much
the reviewer can lean on it once it is. It is computed from the same facts
the gates read, never asked of a model, and it never changes an outcome: a
low-confidence ANSWER is still an ANSWER, it is just the one to read first.
HOLD and REFUSE carry no confidence, because there is no answer to be
confident in.

Four factors, each in [0, 1], each with the sentence a reviewer sees:
  relevance   share of the question's subject terms the claim covers
  evidence    the strongest evidence class behind the claim, and whether a
              machine check (a Vanta test, a dated check) stands behind it
  freshness   how long the claim stays valid; inside 30 days it decays
  provenance  a verbatim reuse of an answer a person approved, or a fresh
              draft from the claim
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .models import CERT_EVIDENCE_KINDS, Claim

WEIGHTS = {"relevance": 0.40, "evidence": 0.25, "freshness": 0.15, "provenance": 0.20}
HIGH, MEDIUM = 0.85, 0.70
EVIDENCE_CHECK_DAYS = 90         # a dated evidence check older than this no longer counts as checked
FRESH_DAYS = 30                  # validity left below this lowers freshness linearly
DOCUMENT_KINDS = {"policy", "standard", "report", "config"}


@dataclass
class Confidence:
    score: float
    band: str                                  # high | medium | low
    factors: dict[str, float] = field(default_factory=dict)
    basis: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"score": self.score, "band": self.band, "factors": dict(self.factors), "basis": list(self.basis)}


def _evidence(claim: Claim, today: date) -> tuple[float, str]:
    kinds = {e.kind for e in claim.evidence_refs}
    checked = [e for e in claim.evidence_refs if e.checked_on and (today - e.checked_on).days <= EVIDENCE_CHECK_DAYS]
    if "vanta_test" in kinds or checked:
        return 1.0, "evidence is machine-checked (a Vanta test or a check within 90 days)"
    if kinds & CERT_EVIDENCE_KINDS:
        return 0.9, "evidence is a certificate or attestation, not checked in the last 90 days"
    if kinds & DOCUMENT_KINDS:
        return 0.75, "evidence is a controlled document (policy, standard, report or config)"
    return 0.5, "evidence is a statement only; nothing independent stands behind it"


def compute(claim: Claim, coverage: float, reused: bool, today: date) -> Confidence:
    relevance = max(0.0, min(1.0, coverage))
    evidence, ev_reason = _evidence(claim, today)
    days_left = (claim.valid_until - today).days
    freshness = 1.0 if days_left >= FRESH_DAYS else max(0.0, days_left / FRESH_DAYS)
    provenance = 1.0 if reused else 0.7
    factors = {"relevance": round(relevance, 3), "evidence": evidence, "freshness": round(freshness, 3),
               "provenance": provenance}
    score = round(sum(WEIGHTS[k] * v for k, v in factors.items()), 3)
    band = "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"
    basis = [
        f"the claim covers {round(relevance * 100)}% of the question's subject terms",
        ev_reason,
        (f"the claim is valid for {days_left} more days" if days_left >= FRESH_DAYS
         else f"the claim expires in {days_left} days; re-verify before relying on it"),
        ("a person approved this exact answer before" if reused
         else "drafted from the claim; no person has approved this wording yet"),
    ]
    return Confidence(score=score, band=band, factors=factors, basis=basis)
