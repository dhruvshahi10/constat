"""Claims: read, propose, approve, reject, freshness. Domain rules live in the
store (second-person approval, hygiene, no-op refusal); this router maps them
to HTTP."""
from __future__ import annotations

from datetime import date
from typing import Any

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from constat.claims import Audience, Claim, ClaimStore
from constat.claims import author, importer
from constat.intake import parsers

from ..auth import CallerPrincipal, current_principal, require
from ..deps import get_claim_store, get_settings
from ..settings import Settings

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


MAX_IMPORT = 6 * 1024 * 1024


def _domain_owners(store: ClaimStore) -> dict[str, str]:
    out: dict[str, list[str]] = {}
    for c in store.list():
        for t in c.topics:
            out.setdefault(t.lower(), []).append(c.owner)
    return {k: max(set(v), key=v.count) for k, v in out.items()}


class CommitRow(BaseModel):
    ordinal: int
    action: str
    owner: str | None = Field(default=None, max_length=200)


class CommitBody(BaseModel):
    rows: list[CommitRow] = Field(default_factory=list, max_length=2000)


@router.post("/import", status_code=201)
async def import_preview(file: UploadFile = File(...), customer: str = Form(""), audience: str = Form("nda"),
                         p: CallerPrincipal = Depends(require("reviewer")),
                         store: ClaimStore = Depends(get_claim_store), settings: Settings = Depends(get_settings)):
    """Preview: an answered questionnaire becomes proposed claims and reusable
    answers. Nothing is written until the commit."""
    if audience not in ("public", "nda", "internal"):
        raise HTTPException(status_code=422, detail={"error": "audience must be public, nda or internal", "code": "INVALID"})
    chunks, size = [], 0
    while True:
        chunk = await file.read(256 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_IMPORT:
            raise HTTPException(status_code=413, detail={"error": "file over 6MB", "code": "TOO_LARGE"})
        chunks.append(chunk)
    name = file.filename or "import"
    if not name.lower().endswith((".xlsx", ".xlsm", ".csv")):
        raise HTTPException(status_code=422, detail={"error": "import needs an xlsx or csv with a response column",
                                                     "code": "UNPARSEABLE"})
    with tempfile.TemporaryDirectory() as tmp:
        try:
            parsed = await run_in_threadpool(parsers.parse, name, b"".join(chunks), Path(tmp))
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e), "code": "UNPARSEABLE"})
    if not any(q.answer for q in parsed.questions):
        raise HTTPException(status_code=422, detail={"error": "no answered rows: the file has no filled response column",
                                                     "code": "NO_ANSWERS"})
    prev = await run_in_threadpool(
        importer.preview, parsed.questions, store, filename=Path(name).name[:120],
        customer=(customer or "unknown")[:200], audience=Audience(audience), actor=p.email, today=date.today(),
        domain_owners=_domain_owners(store))
    importer.PreviewStore(Path(settings.claim_store_path)).save(prev)
    return prev.to_dict()


@router.post("/import/{preview_id}/commit")
def import_commit(preview_id: str, body: CommitBody, p: CallerPrincipal = Depends(require("reviewer")),
                  store: ClaimStore = Depends(get_claim_store), settings: Settings = Depends(get_settings)):
    try:
        prev = importer.PreviewStore(Path(settings.claim_store_path)).load(preview_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": "no such import preview", "code": "NOT_FOUND"})
    res = importer.commit(prev, {r.ordinal: r.action for r in body.rows}, store, actor=p.email, today=date.today(),
                          owners={r.ordinal: r.owner for r in body.rows if r.owner})
    return res.__dict__


class AuthorBody(BaseModel):
    source_id: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=author.MAX_SOURCE_CHARS)
    title: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=500)
    kind: str = "statement"
    products: list[str] = Field(default_factory=list, max_length=8)
    owner: str = Field(default="", max_length=200)
    audience: str = "nda"


def _author_extractor(settings: Settings) -> author.ClaimAuthor:
    import os
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if settings.is_dev or not key:
        return author.SentenceAuthor()
    return author.HaikuAuthor(key)


@router.post("/author", status_code=201)
def author_claims(body: AuthorBody, p: CallerPrincipal = Depends(require("reviewer")),
                  store: ClaimStore = Depends(get_claim_store), settings: Settings = Depends(get_settings)):
    """A source document becomes draft claims, each with the quoted span it
    came from, opened as proposals a second person approves. Never answers."""
    if body.audience not in ("public", "nda", "internal"):
        raise HTTPException(status_code=422, detail={"error": "audience must be public, nda or internal", "code": "INVALID"})
    try:
        doc = author.SourceDoc(source_id=body.source_id, version=body.version, text=body.text, title=body.title,
                               url=body.url, kind=body.kind, products=body.products)
    except ValueError as e:
        raise _domain_error(e)
    run = author.author_document(doc, _author_extractor(settings), store, actor=p.email, today=date.today(),
                                 owner=body.owner, audience=Audience(body.audience))
    if run.failed:
        raise HTTPException(status_code=422, detail={
            "error": "the source was not drafted: " + ("; ".join(run.quarantine) or
                                                      "; ".join(s["reason"] for s in run.skipped) or "extractor failed"),
            "code": "QUARANTINED" if run.quarantine else "AUTHOR_FAILED"})
    return run.to_dict()


@router.get("/{claim_id}")
def get_claim(claim_id: str, _: CallerPrincipal = Depends(current_principal),
              store: ClaimStore = Depends(get_claim_store)):
    c = store.get(claim_id)
    if c is None:
        raise HTTPException(status_code=404, detail={"error": f"no claim {claim_id}", "code": "NOT_FOUND"})
    d = c.to_dict()
    d["usable"], d["unusable_reason"] = c.is_usable(date.today(), Audience.INTERNAL)
    return d
