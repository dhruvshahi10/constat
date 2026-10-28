"""Claims: read, propose, approve, reject, freshness. Domain rules live in the
store (second-person approval, hygiene, no-op refusal); this router maps them
to HTTP."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from constat.claims import Audience, Claim, ClaimStore

from ..auth import CallerPrincipal, current_principal, require
from ..deps import get_claim_store

router = APIRouter(prefix="/v1/claims", tags=["claims"])


class ProposeBody(BaseModel):
    claim: dict[str, Any]
    reason: str = Field(min_length=3, max_length=500)


class DecisionBody(BaseModel):
    reason: str = ""


def _domain_error(e: Exception) -> HTTPException:
    code = {"ValueError": "INVALID", "PermissionError": "FORBIDDEN", "KeyError": "NOT_FOUND"}.get(
        type(e).__name__, "ERROR")
    status = {"INVALID": 422, "FORBIDDEN": 403, "NOT_FOUND": 404}.get(code, 400)
    return HTTPException(status_code=status, detail={"error": str(e), "code": code})


@router.get("")
def list_claims(audience: str | None = None, status: str | None = None,
                _: CallerPrincipal = Depends(current_principal),
                store: ClaimStore = Depends(get_claim_store)):
    today = date.today()
    out = []
    for c in store.list():
        if status and c.status.value != status:
            continue
        if audience and not Audience(audience).may_receive(c.audience):
            continue
        d = c.to_dict()
        d["usable"], d["unusable_reason"] = c.is_usable(today, Audience.INTERNAL)
        out.append(d)
    return {"claims": out, "count": len(out)}


@router.get("/freshness")
def freshness(expiring_days: int = 30, _: CallerPrincipal = Depends(current_principal),
              store: ClaimStore = Depends(get_claim_store)):
    return {"as_of": date.today().isoformat(), "by_owner": store.freshness_digest(date.today(), expiring_days)}


@router.get("/proposals")
def proposals(_: CallerPrincipal = Depends(current_principal),
              store: ClaimStore = Depends(get_claim_store)):
    return {"proposals": [p.to_dict() for p in store.pending()]}


@router.post("/propose", status_code=201)
def propose(body: ProposeBody, p: CallerPrincipal = Depends(require("reviewer")),
            store: ClaimStore = Depends(get_claim_store)):
    try:
        claim = Claim.from_dict(body.claim)
        prop = store.propose(claim, actor=p.email, reason=body.reason, today=date.today())
    except (ValueError, KeyError, TypeError) as e:
        raise _domain_error(ValueError(str(e)))
    return prop.to_dict()


@router.post("/proposals/{proposal_id}/approve")
def approve(proposal_id: str, p: CallerPrincipal = Depends(require("owner")),
            store: ClaimStore = Depends(get_claim_store)):
    try:
        claim = store.approve(proposal_id, approver=p.email, today=date.today())
    except (ValueError, PermissionError, KeyError) as e:
        raise _domain_error(e)
    return claim.to_dict()


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: str, body: DecisionBody, p: CallerPrincipal = Depends(require("owner")),
           store: ClaimStore = Depends(get_claim_store)):
    try:
        prop = store.reject(proposal_id, approver=p.email, today=date.today(), reason=body.reason)
    except (ValueError, KeyError) as e:
        raise _domain_error(e)
    return prop.to_dict()


@router.get("/{claim_id}")
def get_claim(claim_id: str, _: CallerPrincipal = Depends(current_principal),
              store: ClaimStore = Depends(get_claim_store)):
    c = store.get(claim_id)
    if c is None:
        raise HTTPException(status_code=404, detail={"error": f"no claim {claim_id}", "code": "NOT_FOUND"})
    d = c.to_dict()
    d["usable"], d["unusable_reason"] = c.is_usable(date.today(), Audience.INTERNAL)
    return d
