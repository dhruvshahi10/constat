"""Trust preview: what the public trust centre would say, generated from
public-audience, verified, fresh claims. Publishing stays a human action."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from constat.claims import Audience, ClaimStore

from ..auth import CallerPrincipal, current_principal
from ..deps import get_claim_store

router = APIRouter(prefix="/v1/trust", tags=["trust"])


@router.get("/preview")
def preview(_: CallerPrincipal = Depends(current_principal), store: ClaimStore = Depends(get_claim_store)):
    today = date.today()
    entries = []
    for c in store.list():
        if c.audience != Audience.PUBLIC or not c.is_usable(today, Audience.PUBLIC)[0]:
            continue
        checked = [e.checked_on for e in c.evidence_refs if e.checked_on]
        last = max(checked).isoformat() if checked else (c.updated_on.isoformat() if c.updated_on else c.valid_from.isoformat())
        entries.append({"claim_id": c.claim_id, "statement": c.statement,
                        "exceptions": c.exceptions, "evidence": [f"{e.kind}: {e.ref}" for e in c.evidence_refs],
                        "framework_map": c.framework_map, "last_verified": last,
                        "valid_until": c.valid_until.isoformat()})
    entries.sort(key=lambda e: e["claim_id"])
    return {"entries": entries, "count": len(entries), "as_of": today.isoformat(),
            "note": "Preview only. Publishing to the trust centre is a human action and never automated."}
