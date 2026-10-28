"""What happens when the sole reviewer is unreachable.

After 72 hours with no review action from the primary reviewer the tenant is
degraded: already-approved answers on unchanged claims keep flowing under the
ladder's rules, everything novel or changed stays held, the account
executive gets a dated status automatically, and anything blocking a deal
escalates to the named backup with a one-page summary. Nothing is ever
auto-shipped at a lower bar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..persist import DegradationState, MetricEvent, Repository, State, ulid
from ..persist.models import now_iso
from .ranking import age_days

IDLE_HOURS = 72


@dataclass
class Escalation:
    deal_id: str | None
    customer: str
    items: list[dict] = field(default_factory=list)


@dataclass
class DegradationReport:
    mode: str
    primary_reviewer: str
    backup_reviewer: str
    last_review_at: str | None
    idle_hours: float | None
    entered_at: str | None
    held_count: int
    flowing_count: int
    ae_status: list[dict]
    escalations: list[Escalation]

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["escalations"] = [e.__dict__ for e in self.escalations]
        return d


def _state(repo: Repository, tenant: str) -> DegradationState:
    return repo.get("degradation_state", tenant) or DegradationState(tenant=tenant)


def set_reviewers(repo: Repository, tenant: str, primary: str = "", backup: str = "", ladder_level: int | None = None) -> DegradationState:
    st = _state(repo, tenant)
    if primary:
        st.primary_reviewer = primary
    if backup:
        st.backup_reviewer = backup
    if ladder_level is not None:
        if ladder_level not in (1, 2, 3):
            raise ValueError("ladder level is 1, 2 or 3")
        st.ladder_level = ladder_level
    repo.upsert("degradation_state", st)
    return st


def last_primary_action(repo: Repository, tenant: str, primary: str) -> str | None:
    # transitions are recorded under the same actor; only a decision counts as a review action
    acts = [a for a in repo.list("review_actions", {"tenant": tenant, "actor": primary}, order="at desc", limit=200)
            if a.action in ("approve", "edit", "route", "reject", "send", "bulk_approve")]
    return acts[0].at if acts else None


def evaluate(repo: Repository, tenant: str, now: datetime | None = None) -> DegradationReport:
    now = now or datetime.now(timezone.utc)
    st = _state(repo, tenant)
    last = last_primary_action(repo, tenant, st.primary_reviewer) if st.primary_reviewer else None
    last = last or st.last_review_at
    idle = None
    if last:
        dt = datetime.fromisoformat(last)
        dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        idle = round((now - dt).total_seconds() / 3600, 1)
    degraded = bool(st.primary_reviewer) and (idle is None or idle >= IDLE_HOURS)
    if degraded and st.mode != "degraded":
        st.mode, st.entered_at = "degraded", now_iso()
        repo.upsert("degradation_state", st)
        repo.insert("metric_events", MetricEvent(id=ulid(), tenant=tenant, kind="degraded", value_num=1.0,
                                                 payload_json={"idle_hours": idle}))
    elif not degraded and st.mode == "degraded":
        st.mode, st.entered_at = "normal", None
        repo.upsert("degradation_state", st)
    if last and last != st.last_review_at:
        st.last_review_at = last
        repo.upsert("degradation_state", st)

    held = repo.list("question_items", {"tenant": tenant, "state": [State.HELD, State.REVIEW, State.REFUSED]}, limit=50000)
    approved = repo.list("question_items", {"tenant": tenant, "state": State.APPROVED}, limit=50000)
    qnrs = {q.id: q for q in repo.list("questionnaires", {"tenant": tenant}, limit=5000)}

    ae_status: dict[str, dict] = {}
    escalations: dict[str, Escalation] = {}
    for it in held:
        q = qnrs.get(it.questionnaire_id)
        key = q.deal_id or (q.id if q else "unknown")
        row = ae_status.setdefault(key, {"deal_id": q.deal_id if q else None, "customer": q.customer if q else "",
                                         "held": 0, "oldest_days": 0.0, "status_date": now.date().isoformat()})
        row["held"] += 1
        row["oldest_days"] = max(row["oldest_days"], round(age_days(it, now), 1))
        if degraded and it.blocks_deal:
            e = escalations.setdefault(key, Escalation(deal_id=q.deal_id if q else None, customer=q.customer if q else ""))
            e.items.append({"item_id": it.id, "question": it.text[:140], "difficulty": it.difficulty,
                            "route": it.route, "age_days": round(age_days(it, now), 1)})
    return DegradationReport(
        mode="degraded" if degraded else "normal", primary_reviewer=st.primary_reviewer,
        backup_reviewer=st.backup_reviewer, last_review_at=last, idle_hours=idle, entered_at=st.entered_at,
        held_count=len(held), flowing_count=len(approved), ae_status=list(ae_status.values()),
        escalations=list(escalations.values()))


def record_status_sent(repo: Repository, tenant: str) -> None:
    st = _state(repo, tenant)
    st.last_status_sent_at = now_iso()
    repo.upsert("degradation_state", st)
