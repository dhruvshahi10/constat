from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from constat.persist import MetricEvent, Repository, ulid
from constat.workflow import degradation as dg
from constat.workflow.metrics import compute

from datetime import date

from constat.claims import Audience, ClaimStore

from ..auth import CallerPrincipal, current_principal, require
from ..deps import get_claim_store, get_repo

router = APIRouter(prefix="/v1/metrics", tags=["metrics"])


class ShippedWrongBody(BaseModel):
    item_id: str
    note: str = Field(min_length=3, max_length=1000)


@router.get("")
def metrics(deal_id: str | None = None, since: str | None = None,
            p: CallerPrincipal = Depends(current_principal), repo: Repository = Depends(get_repo),
            store: ClaimStore = Depends(get_claim_store)):
    m = compute(repo, p.tenant, deal_id=deal_id, since=since)
    claims = store.list()
    fresh = sum(1 for c in claims if c.is_usable(date.today(), Audience.INTERNAL)[0])
    m["claim_fresh_share"] = round(fresh / len(claims), 3) if claims else None
    m["cost_per_100_usd"] = round(m["model_cost_usd"] / m["questions"] * 100, 4) if m["questions"] else 0.0
    return m


@router.post("/shipped-wrong", status_code=201)
def shipped_wrong(body: ShippedWrongBody, p: CallerPrincipal = Depends(require("reviewer")),
                  repo: Repository = Depends(get_repo)):
    it = repo.get("question_items", body.item_id)
    if it is None or it.tenant != p.tenant:
        raise HTTPException(status_code=404, detail={"error": "no such question", "code": "NOT_FOUND"})
    ev = MetricEvent(id=ulid(), tenant=p.tenant, kind="shipped_wrong", item_id=it.id, difficulty=it.difficulty,
                     value_num=1.0, payload_json={"note": body.note, "actor": p.email, "claim_id": it.claim_id,
                                                  "claim_version_hash": it.claim_version_hash})
    repo.insert("metric_events", ev)
    return {"recorded": True, "stop_signal": True, "event_id": ev.id}


degradation_router = APIRouter(prefix="/v1/degradation", tags=["degradation"])


class ReviewersBody(BaseModel):
    primary_reviewer: str = ""
    backup_reviewer: str = ""
    ladder_level: int | None = None


@degradation_router.get("")
def state(p: CallerPrincipal = Depends(current_principal), repo: Repository = Depends(get_repo)):
    rep = dg.evaluate(repo, p.tenant)
    st = repo.get("degradation_state", p.tenant)
    return rep.to_dict() | {"ladder_level": st.ladder_level if st else 1}


@degradation_router.post("/backup")
def reviewers(body: ReviewersBody, p: CallerPrincipal = Depends(require("owner")), repo: Repository = Depends(get_repo)):
    try:
        st = dg.set_reviewers(repo, p.tenant, body.primary_reviewer, body.backup_reviewer, body.ladder_level)
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": str(e), "code": "INVALID"})
    return st.to_row()


@degradation_router.post("/status-sent")
def status_sent(p: CallerPrincipal = Depends(require("reviewer")), repo: Repository = Depends(get_repo)):
    dg.record_status_sent(repo, p.tenant)
    return {"ok": True}
