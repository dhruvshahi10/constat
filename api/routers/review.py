"""Review queue and actions."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from constat.claims import Audience, ClaimStore
from constat.persist import Deal, Repository, State, ulid
from constat.workflow import review as rv
from constat.workflow.ranking import rank

from ..auth import CallerPrincipal, require
from ..deps import get_claim_store, get_repo
from ..views import ViewCache, item_view

router = APIRouter(prefix="/v1/review", tags=["review"])


class NoteBody(BaseModel):
    note: str = Field(default="", max_length=1000)


class EditBody(BaseModel):
    answer: str = Field(min_length=3, max_length=4000)
    note: str = Field(default="", max_length=1000)


class RouteBody(BaseModel):
    to: str = Field(min_length=2, max_length=120)
    deadline: str | None = None
    note: str = Field(default="", max_length=1000)


class SendBody(BaseModel):
    customer: str = Field(default="", max_length=200)


class BulkBody(BaseModel):
    item_ids: list[str] = Field(min_length=1, max_length=500)
    spot_checked_ids: list[str] = Field(default_factory=list)


def _ctx(p: CallerPrincipal, repo: Repository, store: ClaimStore, item=None) -> rv.ReviewContext:
    audience = Audience.NDA
    if item is not None:
        q = repo.get("questionnaires", item.questionnaire_id)
        if q:
            audience = Audience(q.audience)
    return rv.ReviewContext(repo=repo, store=store, actor=p.email, today=date.today(), audience=audience)


def _item(repo: Repository, item_id: str, p: CallerPrincipal):
    it = repo.get("question_items", item_id)
    if it is None or it.tenant != p.tenant:
        raise HTTPException(status_code=404, detail={"error": "no such question", "code": "NOT_FOUND"})
    return it


def _err(e: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail={"error": str(e), "code": "REVIEW_RULE"})


def _row(it, score=None, repo: Repository | None = None) -> dict:
    return item_view(it, ViewCache(repo or _REPO_FALLBACK()), score)


def _REPO_FALLBACK():
    return get_repo()


@router.get("/queue")
def queue(state: str = "REVIEW,HELD,APPROVED", p: CallerPrincipal = Depends(require("reviewer")),
          repo: Repository = Depends(get_repo)):
    states = [State(s.strip()) for s in state.split(",") if s.strip()]
    items = repo.list("question_items", {"tenant": p.tenant, "state": states}, limit=5000)
    deals: dict[str, Deal] = {}
    for q in repo.list("questionnaires", {"tenant": p.tenant}, limit=1000):
        if q.deal_id:
            d = repo.get("deals", q.deal_id)
            if d:
                deals[q.id] = d
    ranked = rank(items, deals)
    cache = ViewCache(repo)
    return {"items": [item_view(it, cache, s) for it, s in ranked], "count": len(ranked)}


@router.post("/{item_id}/approve")
def approve(item_id: str, body: NoteBody | None = None, p: CallerPrincipal = Depends(require("reviewer")),
            repo: Repository = Depends(get_repo), store: ClaimStore = Depends(get_claim_store)):
    it = _item(repo, item_id, p)
    try:
        return _row(rv.approve(_ctx(p, repo, store, it), it, body.note if body else ""), repo=repo)
    except (rv.ReviewError, ValueError) as e:
        raise _err(e)


@router.post("/{item_id}/edit")
def edit(item_id: str, body: EditBody, p: CallerPrincipal = Depends(require("reviewer")),
         repo: Repository = Depends(get_repo), store: ClaimStore = Depends(get_claim_store)):
    it = _item(repo, item_id, p)
    try:
        it, verdict = rv.edit(_ctx(p, repo, store, it), it, body.answer, body.note)
    except (rv.ReviewError, ValueError) as e:
        raise _err(e)
    proposal = next((pr.to_dict() for pr in store.pending()
                     if pr.claim.claim_id == it.claim_id and pr.actor == p.email), None)
    return {"item": _row(it, repo=repo), "verdict": verdict, "proposal": proposal}


@router.post("/{item_id}/route")
def route(item_id: str, body: RouteBody, p: CallerPrincipal = Depends(require("reviewer")),
          repo: Repository = Depends(get_repo), store: ClaimStore = Depends(get_claim_store)):
    it = _item(repo, item_id, p)
    try:
        return _row(rv.route(_ctx(p, repo, store, it), it, body.to, body.deadline, body.note), repo=repo)
    except (rv.ReviewError, ValueError) as e:
        raise _err(e)


@router.post("/{item_id}/reject")
def reject(item_id: str, body: NoteBody, p: CallerPrincipal = Depends(require("reviewer")),
           repo: Repository = Depends(get_repo), store: ClaimStore = Depends(get_claim_store)):
    it = _item(repo, item_id, p)
    try:
        return _row(rv.reject(_ctx(p, repo, store, it), it, body.note), repo=repo)
    except (rv.ReviewError, ValueError) as e:
        raise _err(e)


@router.post("/{item_id}/send")
def send(item_id: str, body: SendBody | None = None, p: CallerPrincipal = Depends(require("reviewer")),
         repo: Repository = Depends(get_repo), store: ClaimStore = Depends(get_claim_store)):
    it = _item(repo, item_id, p)
    customer = (body.customer if body else "") or (repo.get("questionnaires", it.questionnaire_id).customer)
    try:
        return _row(rv.send(_ctx(p, repo, store, it), it, customer), repo=repo)
    except (rv.ReviewError, ValueError) as e:
        raise _err(e)


@router.post("/bulk-approve-reused")
def bulk(body: BulkBody, p: CallerPrincipal = Depends(require("reviewer")),
         repo: Repository = Depends(get_repo), store: ClaimStore = Depends(get_claim_store)):
    items = [_item(repo, i, p) for i in body.item_ids]
    try:
        done = rv.bulk_approve_reused(_ctx(p, repo, store, items[0] if items else None), items, set(body.spot_checked_ids))
    except (rv.ReviewError, ValueError) as e:
        raise _err(e)
    return {"approved": [_row(i, repo=repo) for i in done], "spot_checks_required": rv.spot_checks_required(len(items))}


deals_router = APIRouter(prefix="/v1/deals", tags=["deals"])


class DealBody(BaseModel):
    customer: str = Field(min_length=1, max_length=200)
    value_usd: int = Field(default=0, ge=0)
    close_date: str | None = None
    ae_email: str = ""
    approved_customer: bool = False


@deals_router.get("")
def list_deals(p: CallerPrincipal = Depends(require("reviewer")), repo: Repository = Depends(get_repo)):
    return {"deals": [d.to_row() for d in repo.list("deals", {"tenant": p.tenant}, order="created_at desc", limit=500)]}


@deals_router.post("", status_code=201)
def create_deal(body: DealBody, p: CallerPrincipal = Depends(require("reviewer")), repo: Repository = Depends(get_repo)):
    d = Deal(id=ulid(), tenant=p.tenant, **body.model_dump())
    repo.insert("deals", d)
    return d.to_row()
