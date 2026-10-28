"""The automation ladder and the hard limits.

L1  draft plus 100% human review.
L2  auto-send REUSED answers to approved customers when the claim is fresh
    and unchanged since the approved answer.
L3  also auto-send COVERED answers, after four weeks with a low human edit
    rate and zero shipped-wrong.

The hard limits never automate at any level: new contractual commitments,
questions no human has answered before, disclosure of sensitive internals,
publishing to the public trust centre, correcting or declining a customer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..claims import Audience, ClaimStore
from ..persist import Deal, QuestionItem, State

HARD_LIMIT_FLAGS = {"LEGAL_COMMITMENT", "CONTRACTUAL_WORDING", "NO_COVERING_CLAIM", "INJECTION_SUSPECTED",
                    "AUDIENCE_BLOCKED", "CERT_NEEDS_HUMAN", "STALE_CLAIM", "DEPRECATED_CLAIM",
                    "EXCEPTION_OMITTED", "NEW_VALUE_INTRODUCED", "ABSOLUTE_LANGUAGE", "RELEVANCE_LOW",
                    "PARAMETER_MISSING", "DRAFTER_ABSTAINED", "NORMALISE_FAILED"}
L3_MIN_WEEKS = 4
L3_MAX_EDIT_RATE = 0.10


@dataclass
class LadderDecision:
    auto_send: bool
    reason: str


def hard_limit(item: QuestionItem) -> str | None:
    """A reason this item can never be sent without a person, or None."""
    if item.difficulty in ("contractual", "novel"):
        return f"{item.difficulty} questions are always decided by a person"
    hit = HARD_LIMIT_FLAGS & set(item.flags)
    if hit:
        return f"flagged {sorted(hit)}"
    if item.state in (State.HELD, State.REFUSED, State.QUARANTINED):
        return f"item is {item.state.value}"
    return None


def decide(level: int, item: QuestionItem, deal: Deal | None, store: ClaimStore, today: date,
           audience: Audience, metrics: dict | None = None) -> LadderDecision:
    limit = hard_limit(item)
    if limit:
        return LadderDecision(False, limit)
    if level <= 1:
        return LadderDecision(False, "level 1: every answer is reviewed by a person")
    if deal is None or not deal.approved_customer:
        return LadderDecision(False, "customer is not approved for automated answers")
    if audience == Audience.PUBLIC:
        return LadderDecision(False, "public-audience answers are published by a person")
    claim = store.get(item.claim_id) if item.claim_id else None
    if claim is None:
        return LadderDecision(False, "no claim behind the answer")
    ok, why = claim.is_usable(today, audience)
    if not ok:
        return LadderDecision(False, f"claim is {why}")
    if item.claim_version_hash != claim.version_hash():
        return LadderDecision(False, "claim changed since the answer was approved")
    if item.difficulty == "reused":
        return LadderDecision(True, "level 2: reused answer, approved customer, claim fresh and unchanged")
    if level >= 3 and item.difficulty == "covered":
        if metrics is None:
            return LadderDecision(False, "level 3 needs four weeks of metrics")
        if metrics.get("shipped_wrong", 0) > 0:
            return LadderDecision(False, "stop signal: an answer shipped wrong")
        rate = metrics.get("human_edit_rate")
        weeks = metrics.get("weeks_observed", 0)
        if rate is None or rate > L3_MAX_EDIT_RATE or weeks < L3_MIN_WEEKS:
            return LadderDecision(False, f"level 3 needs edit rate at or below {L3_MAX_EDIT_RATE} over {L3_MIN_WEEKS} weeks")
        return LadderDecision(True, "level 3: covered answer under a low edit rate with zero shipped wrong")
    return LadderDecision(False, f"level {level} does not automate {item.difficulty} answers")
