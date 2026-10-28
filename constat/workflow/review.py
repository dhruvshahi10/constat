"""Review actions: the only way an answer becomes final.

approve   REVIEW -> APPROVED; the answer is written back to the claim as an
          approved answer, so the next matching question is REUSED.
edit      the edited text is re-gated like any draft; if it passes it is
          approved and written back; a material rewrite also opens a proposal
          to the claim owner so the claim itself can catch up.
route     -> HELD with a named route and deadline; a follow-up event.
reject    -> REFUSED.
send      APPROVED -> SENT; the sent-answer record pins the claim version.
bulk      REUSED items only, after spot checks.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..claims import ApprovedAnswer, Audience, ClaimStore
from ..claims.gates import gate
from ..claims.match import ClaimMatcher
from ..claims.models import Claim
from ..claims.store import SentAnswerRecord
from ..persist import MetricEvent, QuestionItem, Repository, ReviewAction, State, ulid
from .diff import edit_distance_ratio
from .items import transition

MATERIAL_EDIT = 0.30          # edit distance ratio above which the claim owner is asked to update the claim
SPOT_CHECK_MIN = 3
SPOT_CHECK_SHARE = 0.10


class ReviewError(ValueError):
    pass


@dataclass
class ReviewContext:
    repo: Repository
    store: ClaimStore
    actor: str
    today: date
    audience: Audience = Audience.NDA


def _action(ctx: ReviewContext, item: QuestionItem, action: str, note: str = "",
            before: str | None = None, after: str | None = None) -> None:
    ctx.repo.insert("review_actions", ReviewAction(id=ulid(), item_id=item.id, tenant=item.tenant,
                                                   actor=ctx.actor, action=action, note=note,
                                                   before_answer=before, after_answer=after))


def _metric(ctx: ReviewContext, item: QuestionItem, kind: str, value: float = 0.0, **payload) -> None:
    ctx.repo.insert("metric_events", MetricEvent(id=ulid(), tenant=item.tenant, kind=kind, item_id=item.id,
                                                 difficulty=item.difficulty, value_num=value,
                                                 payload_json=payload | {"actor": ctx.actor}))


def _writeback(ctx: ReviewContext, item: QuestionItem, answer: str) -> None:
    if not item.claim_id or not hasattr(ctx.store, "add_approved_answer"):
        return
    ctx.store.add_approved_answer(item.claim_id, ApprovedAnswer(
        question=item.text, answer=answer, approver=ctx.actor, approved_on=ctx.today,
        audience=ctx.audience), approver=ctx.actor, today=ctx.today)


def approve(ctx: ReviewContext, item: QuestionItem, note: str = "") -> QuestionItem:
    if item.state not in (State.REVIEW, State.HELD):
        raise ReviewError(f"{item.id} is {item.state.value}; only REVIEW or HELD items can be approved")
    if not item.draft_answer:
        raise ReviewError(f"{item.id} has no draft to approve; edit it instead")
    if item.state == State.HELD and item.verdict_json.get("outcome") == "HOLD_HUMAN" \
            and "LEGAL_COMMITMENT" in item.flags:
        raise ReviewError("a legal commitment is never approved from the queue; route it to LEGAL")
    answer = item.draft_answer
    transition(ctx.repo, item, State.APPROVED, ctx.actor, note, final_answer=answer)
    _action(ctx, item, "approve", note, before=answer, after=answer)
    _metric(ctx, item, "human_edit", 0.0)
    _writeback(ctx, item, answer)
    return item


def edit(ctx: ReviewContext, item: QuestionItem, new_answer: str, note: str = "") -> tuple[QuestionItem, dict]:
    """Returns the item and the verdict the edited answer received."""
    if item.state not in (State.REVIEW, State.HELD, State.REFUSED):
        raise ReviewError(f"{item.id} is {item.state.value}; cannot edit")
    new_answer = " ".join((new_answer or "").split())
    if len(new_answer) < 3:
        raise ReviewError("an edited answer needs text")
    matcher = ClaimMatcher(ctx.store)
    matches = matcher.match(item.text, ctx.today, ctx.audience)
    v = gate(item.text, matches, ctx.today, ctx.audience, candidate_answer=new_answer, domain=item.domain)
    before = item.draft_answer or ""
    ratio = edit_distance_ratio(before, new_answer)
    _action(ctx, item, "edit", note, before=before, after=new_answer)
    _metric(ctx, item, "human_edit", ratio)
    if v.outcome == "ANSWER":
        transition(ctx.repo, item, State.APPROVED, ctx.actor, note, final_answer=new_answer,
                   draft_answer=new_answer, verdict_json=v.to_dict(), flags=sorted(set(item.flags) | set(v.flags)),
                   claim_id=v.claim_id, claim_version_hash=v.claim_version_hash, difficulty=v.difficulty.value)
        _writeback(ctx, item, new_answer)
        if ratio >= MATERIAL_EDIT and v.claim_id:
            _propose_claim_update(ctx, v.claim_id, item, new_answer)
    else:
        target = State.HELD if v.outcome == "HOLD_HUMAN" else State.REFUSED
        transition(ctx.repo, item, target, ctx.actor, "; ".join(v.gaps)[:300], draft_answer=new_answer,
                   verdict_json=v.to_dict(), flags=sorted(set(item.flags) | set(v.flags)), route=v.route)
    return item, v.to_dict()


def _propose_claim_update(ctx: ReviewContext, claim_id: str, item: QuestionItem, answer: str) -> None:
    c = ctx.store.get(claim_id)
    if c is None:
        return
    updated = Claim.from_dict(c.to_dict())
    updated.notes = (c.notes + "\n" if c.notes else "") + \
        f"Reviewer {ctx.actor} materially rewrote an answer on {ctx.today.isoformat()} for: " \
        f"\"{item.text[:120]}\". Edited answer: \"{answer[:300]}\". Consider updating the statement or exceptions."
    updated.keywords = sorted(set(c.keywords) | {w for w in item.text.lower().split() if len(w) > 6})[:40]
    try:
        ctx.store.propose(updated, actor=ctx.actor,
                          reason=f"material reviewer edit on item {item.id}", today=ctx.today)
    except ValueError:
        pass  # a no-op proposal means the claim already carries this; nothing to ask the owner


def route(ctx: ReviewContext, item: QuestionItem, to: str, deadline: Optional[str] = None, note: str = "") -> QuestionItem:
    if item.state in (State.SENT,):
        raise ReviewError("a sent answer cannot be routed")
    if not to or len(to) > 120:
        raise ReviewError("route needs a recipient such as OWNER:<email> or LEGAL")
    if item.state != State.HELD:
        transition(ctx.repo, item, State.HELD, ctx.actor, note, route=to)
    else:
        ctx.repo.update("question_items", item.id, {"route": to})
        item.route = to
    _action(ctx, item, "route", f"{to}" + (f" by {deadline}" if deadline else "") + (f": {note}" if note else ""))
    _metric(ctx, item, "follow_up", 1.0, route=to, deadline=deadline)
    return item


def reject(ctx: ReviewContext, item: QuestionItem, note: str) -> QuestionItem:
    if not note or len(note) < 3:
        raise ReviewError("a rejection needs a reason")
    transition(ctx.repo, item, State.REFUSED, ctx.actor, note)
    _action(ctx, item, "reject", note, before=item.draft_answer)
    return item


def send(ctx: ReviewContext, item: QuestionItem, customer: str) -> QuestionItem:
    if item.state != State.APPROVED or not item.final_answer:
        raise ReviewError(f"{item.id} is {item.state.value}; only APPROVED items are sent")
    transition(ctx.repo, item, State.SENT, ctx.actor, f"sent to {customer}")
    _action(ctx, item, "send", customer, after=item.final_answer)
    _metric(ctx, item, "sent", 1.0, customer=customer)
    ctx.store.record_sent_answer(SentAnswerRecord(
        question=item.text, answer=item.final_answer, claim_ids=[item.claim_id] if item.claim_id else [],
        claim_version_hashes=[item.claim_version_hash] if item.claim_version_hash else [],
        approver=ctx.actor, customer=customer, sent_on=ctx.today, audience=ctx.audience,
        difficulty_class=item.difficulty))
    return item


def spot_checks_required(n: int) -> int:
    return max(SPOT_CHECK_MIN, math.ceil(SPOT_CHECK_SHARE * n)) if n > 0 else 0


def bulk_approve_reused(ctx: ReviewContext, items: list[QuestionItem], spot_checked_ids: set[str]) -> list[QuestionItem]:
    """Approve many REUSED items at once. Refuses unless enough of them were
    spot-checked by hand, and refuses any item that is not a REUSED draft."""
    bad = [i.id for i in items if i.difficulty != "reused" or i.state != State.REVIEW]
    if bad:
        raise ReviewError(f"bulk approval is for REUSED items awaiting review only; refused: {bad[:5]}")
    need = spot_checks_required(len(items))
    checked = {i.id for i in items} & set(spot_checked_ids)
    if len(checked) < need:
        raise ReviewError(f"spot-check {need} of {len(items)} before bulk approval; {len(checked)} checked")
    out = []
    for it in items:
        if len(it.flags) and any(f.startswith(("STALE", "DEPRECATED", "EXCEPTION_OMITTED")) for f in it.flags):
            raise ReviewError(f"{it.id} carries {it.flags}; not eligible")
        transition(ctx.repo, it, State.APPROVED, ctx.actor, "bulk approve (reused)", final_answer=it.draft_answer)
        _action(ctx, it, "bulk_approve", f"spot-checked: {it.id in checked}", before=it.draft_answer, after=it.draft_answer)
        _metric(ctx, it, "human_edit", 0.0, bulk=True, spot_checked=it.id in checked)
        out.append(it)
    return out
