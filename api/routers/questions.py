"""Dry-run verdicts for the command palette and for agents: match, gate,
return what would happen. Nothing is stored except a metric event."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from constat.claims import Audience
from constat.claims.gates import gate
from constat.claims.match import ClaimMatcher
from constat.persist import MetricEvent, Repository, ulid

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
