"""Dry-run verdicts for the command palette and for agents: match, gate,
return what would happen. Nothing is stored except a metric event."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from constat.claims import Audience
from constat.claims.gates import gate
from constat.claims.match import ClaimMatcher
from fastapi import HTTPException

from constat.persist import MetricEvent, Repository, State, ulid
from constat.workflow.diff import word_diff

from ..auth import CallerPrincipal, current_principal
from ..deps import get_matcher, get_repo

router = APIRouter(prefix="/v1/questions", tags=["questions"])


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    audience: str = "nda"
    domain: str = ""
    candidate_answer: str | None = None


@router.post("/ask")
def ask(body: AskBody, p: CallerPrincipal = Depends(current_principal),
        matcher: ClaimMatcher = Depends(get_matcher), repo: Repository = Depends(get_repo)):
    today = date.today()
    audience = Audience(body.audience)
    matches = matcher.match(body.question, today, audience)
    v = gate(body.question, matches, today, audience, candidate_answer=body.candidate_answer,
             domain=body.domain)
    repo.insert("metric_events", MetricEvent(
        id=ulid(), tenant=p.tenant, kind="ask", difficulty=v.difficulty.value,
        payload_json={"outcome": v.outcome, "flags": v.flags, "actor": p.email}))
    return {
        "verdict": v.to_dict(),
        "matches": [{"claim_id": m.claim.claim_id, "score": m.score, "coverage": round(m.coverage, 3),
                     "matched_terms": m.matched_terms, "reused": m.reused is not None}
                    for m in matches],
    }


def _item(repo: Repository, item_id: str, p: CallerPrincipal):
    it = repo.get("question_items", item_id)
    if it is None or it.tenant != p.tenant:
        raise HTTPException(status_code=404, detail={"error": "no such question", "code": "NOT_FOUND"})
    return it


def _last_approved(repo: Repository, it) -> str | None:
    """The most recent SENT or APPROVED answer in this tenant that rested on
    the same claim: what the reviewer compares the new draft against."""
    if not it.claim_id:
        return None
    for prev in repo.list("question_items", {"tenant": it.tenant, "claim_id": it.claim_id,
                                             "state": [State.SENT, State.APPROVED]},
                          order="updated_at desc", limit=5):
        if prev.id != it.id and prev.final_answer:
            return prev.final_answer
    return None


@router.get("/{item_id}")
def get_question(item_id: str, p: CallerPrincipal = Depends(current_principal),
                 repo: Repository = Depends(get_repo), matcher: ClaimMatcher = Depends(get_matcher)):
    it = _item(repo, item_id, p)
    claim = matcher.store.get(it.claim_id) if it.claim_id else None
    last = _last_approved(repo, it)
    actions = repo.list("review_actions", {"item_id": it.id}, order="at asc", limit=200)
    return {"item": it.to_row() | {"verdict_json": it.verdict_json, "flags": it.flags},
            "claim": claim.to_dict() if claim else None,
            "last_approved_answer": last,
            "diff": word_diff(last or "", it.final_answer or it.draft_answer or "") if last else [],
            "actions": [a.to_row() for a in actions]}


@router.get("/{item_id}/diff")
def diff(item_id: str, p: CallerPrincipal = Depends(current_principal), repo: Repository = Depends(get_repo)):
    it = _item(repo, item_id, p)
    last = _last_approved(repo, it)
    return {"last_approved_answer": last, "ops": word_diff(last or "", it.final_answer or it.draft_answer or "")}
