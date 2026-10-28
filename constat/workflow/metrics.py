"""Metrics by difficulty class, never in total.

The headline is time from questionnaire received to security sign-off. The
alarm is the age of the oldest open novel or contractual question per deal.
The stop signal is shipped answers later found wrong."""
from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Optional

from ..persist import Repository, State
from .items import OPEN_HARD
from .ranking import age_days

HARD = {"novel", "contractual"}


def _iso(s: str) -> datetime:
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    return round(vs[min(len(vs) - 1, int(round(0.95 * (len(vs) - 1))))], 1)


def compute(repo: Repository, tenant: str, deal_id: Optional[str] = None,
            since: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    qnrs = repo.list("questionnaires", {"tenant": tenant}, limit=5000)
    if deal_id:
        qnrs = [q for q in qnrs if q.deal_id == deal_id]
    if since:
        qnrs = [q for q in qnrs if q.received_at >= since]
    qids = {q.id for q in qnrs}
    items = [i for i in repo.list("question_items", {"tenant": tenant}, limit=50000) if i.questionnaire_id in qids]

    # by class: counts and resting states
    by_class: dict[str, dict[str, int]] = {}
    for i in items:
        cls = i.difficulty or "unclassified"
        row = by_class.setdefault(cls, {"total": 0, "review": 0, "approved": 0, "sent": 0, "held": 0,
                                        "refused": 0, "quarantined": 0})
        row["total"] += 1
        key = {State.REVIEW: "review", State.APPROVED: "approved", State.SENT: "sent", State.HELD: "held",
               State.REFUSED: "refused", State.QUARANTINED: "quarantined"}.get(i.state)
        if key:
            row[key] += 1

    # oldest open hard question per deal
    oldest: dict[str, dict] = {}
    for i in items:
        if i.state in OPEN_HARD and i.difficulty in HARD:
            q = next((x for x in qnrs if x.id == i.questionnaire_id), None)
            key = (q.deal_id or f"questionnaire:{q.id}") if q else "unknown"
            age = round(age_days(i, now), 2)
            if key not in oldest or age > oldest[key]["age_days"]:
                oldest[key] = {"item_id": i.id, "age_days": age, "difficulty": i.difficulty,
                               "question": i.text[:140], "route": i.route}

    # events
    events = repo.list("metric_events", {"tenant": tenant}, limit=100000)
    item_ids = {i.id for i in items}
    scoped = [e for e in events if (e.item_id in item_ids) or (e.item_id is None and not deal_id)]
    edits = [e.value_num for e in scoped if e.kind == "human_edit"]
    follow_ups = sum(1 for e in scoped if e.kind == "follow_up")
    shipped_wrong = [e for e in scoped if e.kind == "shipped_wrong"]
    latencies = [e.value_num for e in scoped if e.kind == "latency_ms" and e.payload_json.get("stage") == "draft"]
    cost = round(sum(e.value_num for e in scoped if e.kind == "cost_usd"), 4)
    asks = sum(1 for e in scoped if e.kind == "ask")

    # novel questions per month
    novel_by_month: dict[str, int] = {}
    for i in items:
        if i.difficulty == "novel":
            m = i.created_at[:7]
            novel_by_month[m] = novel_by_month.get(m, 0) + 1

    # cycle time: received to last sent, per questionnaire, in hours
    cycle_hours = []
    for q in qnrs:
        sent = [i for i in items if i.questionnaire_id == q.id and i.state == State.SENT]
        if sent and len(sent) == sum(1 for i in items if i.questionnaire_id == q.id and i.state not in (State.REFUSED, State.QUARANTINED)):
            last = max(_iso(i.updated_at) for i in sent)
            cycle_hours.append((last - _iso(q.received_at)).total_seconds() / 3600)

    return {
        "tenant": tenant, "deal_id": deal_id, "as_of": now.isoformat(timespec="seconds"),
        "questionnaires": len(qnrs), "questions": len(items),
        "by_class": by_class,
        "oldest_open_hard": oldest,
        "human_edit_rate": round(sum(1 for e in edits if e > 0) / len(edits), 3) if edits else None,
        "mean_edit_distance": round(statistics.mean(edits), 3) if edits else None,
        "follow_ups_per_questionnaire": round(follow_ups / len(qnrs), 2) if qnrs else 0.0,
        "novel_per_month": novel_by_month,
        "shipped_wrong": len(shipped_wrong),
        "stop_signal": len(shipped_wrong) > 0,
        "cycle_time_hours_median": round(statistics.median(cycle_hours), 1) if cycle_hours else None,
        "p95_draft_latency_ms": _p95(latencies),
        "model_cost_usd": cost,
        "asks": asks,
    }
