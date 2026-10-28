"""Question item state machine. Every item always has exactly one state and
every change is written twice: as a review action (who, why) and as a metric
event (what class, when)."""
from __future__ import annotations

from ..persist import MetricEvent, QuestionItem, Repository, ReviewAction, State, ulid
from ..persist.models import now_iso

TRANSITIONS: dict[State, set[State]] = {
    State.RECEIVED: {State.NORMALISED, State.HELD, State.QUARANTINED},
    State.NORMALISED: {State.MATCHED, State.REFUSED, State.HELD, State.QUARANTINED},
    State.MATCHED: {State.DRAFTED, State.HELD, State.REFUSED},
    State.DRAFTED: {State.REVIEW, State.HELD, State.REFUSED},
    State.REVIEW: {State.APPROVED, State.HELD, State.REFUSED, State.DRAFTED},
    State.HELD: {State.REVIEW, State.DRAFTED, State.REFUSED, State.APPROVED},
    State.REFUSED: {State.HELD, State.DRAFTED},
    State.APPROVED: {State.SENT, State.REVIEW},
    State.SENT: set(),
    State.QUARANTINED: {State.HELD},
}
OPEN_HARD = {State.HELD, State.REFUSED}        # what "oldest open hard question" counts


class IllegalTransition(ValueError):
    pass


def transition(repo: Repository, item: QuestionItem, to: State, actor: str, reason: str = "",
               **fields) -> QuestionItem:
    if to not in TRANSITIONS[item.state]:
        raise IllegalTransition(f"{item.id}: {item.state.value} -> {to.value} is not allowed")
    before = item.state
    fields = {**fields, "state": to, "updated_at": now_iso()}
    repo.update("question_items", item.id, fields)
    for k, v in fields.items():
        setattr(item, k, v)
    repo.insert("review_actions", ReviewAction(id=ulid(), item_id=item.id, tenant=item.tenant,
                                               actor=actor, action="transition",
                                               note=f"{before.value} -> {to.value}" + (f": {reason}" if reason else "")))
    repo.insert("metric_events", MetricEvent(id=ulid(), tenant=item.tenant, kind="item_state",
                                             item_id=item.id, difficulty=item.difficulty,
                                             payload_json={"from": before.value, "to": to.value, "actor": actor}))
    return item
