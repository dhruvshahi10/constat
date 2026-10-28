"""Questionnaires: upload, status, items, quarantine, export, events."""
from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import threading
from datetime import date
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from constat.claims import Audience, ClaimStore
from constat.intake import parsers
from constat.persist import Questionnaire, Repository, State, ulid
from constat.workflow.pipeline2 import PipelineConfig, create_items, process_questionnaire

from ..auth import CallerPrincipal, current_principal, require
from ..deps import get_claim_store, get_repo, get_settings
from ..views import ViewCache, item_view
from ..settings import Settings

router = APIRouter(prefix="/v1/questionnaires", tags=["questionnaires"])
MAX_UPLOAD = 6 * 1024 * 1024
_UPLOAD_DIR = Path(tempfile.gettempdir()) / "constat-uploads"
_LAYOUTS: dict[str, dict] = {}            # questionnaire id -> layout dict (in-process; export needs it)
_LOCK = threading.Lock()


def _owned(repo: Repository, qid: str, p: CallerPrincipal) -> Questionnaire:
    q = repo.get("questionnaires", qid)
    if q is None or q.tenant != p.tenant:
        raise HTTPException(status_code=404, detail={"error": "no such questionnaire", "code": "NOT_FOUND"})
    return q


def _run(repo: Repository, store: ClaimStore, qid: str, audience: str, settings: Settings) -> None:
    cfg = PipelineConfig(today=date.today(), audience=Audience(audience), domain_owners=_domain_owners(store))
    if settings.is_dev or not _anthropic_key():
        pass  # mock normaliser and deterministic drafter by default
    else:
        from constat.claims.drafter import HaikuClaimDrafter
        from constat.intake.normalise import HaikuNormaliser
        cfg.normaliser = HaikuNormaliser(_anthropic_key())
        cfg.drafter = HaikuClaimDrafter(_anthropic_key())
    try:
        process_questionnaire(repo, qid, store, cfg)
    except Exception as e:  # noqa: BLE001 - the run must look failed, never half-done
        repo.update("questionnaires", qid, {"status": f"error: {type(e).__name__}"})


def _anthropic_key() -> str:
    import os
    return os.environ.get("ANTHROPIC_API_KEY", "")


def _domain_owners(store: ClaimStore) -> dict[str, str]:
    """Owner per domain, inferred from the claims: the most common owner of
    claims whose topics or keywords mention the domain word."""
    out: dict[str, list[str]] = {}
    for c in store.list():
        for t in c.topics:
            out.setdefault(t.lower(), []).append(c.owner)
    return {k: max(set(v), key=v.count) for k, v in out.items()}


@router.post("", status_code=202)
async def upload(background: BackgroundTasks, file: UploadFile = File(...), customer: str = Form(""),
                 deal_id: str = Form(""), audience: str = Form("nda"),
                 p: CallerPrincipal = Depends(require("reviewer")), repo: Repository = Depends(get_repo),
                 store: ClaimStore = Depends(get_claim_store), settings: Settings = Depends(get_settings)):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail={"error": "file over 6MB", "code": "TOO_LARGE"})
    if audience not in ("public", "nda", "internal"):
        raise HTTPException(status_code=422, detail={"error": "audience must be public, nda or internal", "code": "INVALID"})
    qid = ulid()
    qdir = _UPLOAD_DIR / p.tenant / qid
    qdir.mkdir(parents=True, exist_ok=True)
    try:
        parsed = parsers.parse(file.filename or "upload", data, qdir)
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": str(e), "code": "UNPARSEABLE"})
    (qdir / "original").write_bytes(data)
    q = Questionnaire(id=qid, tenant=p.tenant, customer=customer or "unknown", filename=file.filename or "upload",
                      sha256=hashlib.sha256(data).hexdigest(), source_kind=parsed.source_kind,
                      audience=audience, deal_id=deal_id or None)
    repo.insert("questionnaires", q)
    create_items(repo, qid, p.tenant, parsed.questions)
    with _LOCK:
        _LAYOUTS[qid] = parsed.layout.__dict__
    background.add_task(_run, repo, store, qid, audience, settings)
    return {"id": qid, "questions": len(parsed.questions), "source_kind": parsed.source_kind,
            "warnings": parsed.warnings, "status": "received"}


@router.get("")
def list_questionnaires(p: CallerPrincipal = Depends(current_principal), repo: Repository = Depends(get_repo)):
    rows = repo.list("questionnaires", {"tenant": p.tenant}, order="received_at desc", limit=200)
    return {"questionnaires": [_summary(repo, q) for q in rows]}


def _summary(repo: Repository, q: Questionnaire) -> dict:
    counts: dict[str, int] = {}
    for it in repo.list("question_items", {"questionnaire_id": q.id}, limit=5000):
        counts[it.state.value] = counts.get(it.state.value, 0) + 1
    return q.to_row() | {"counts": counts, "total": sum(counts.values())}


@router.get("/{qid}")
def get_questionnaire(qid: str, p: CallerPrincipal = Depends(current_principal), repo: Repository = Depends(get_repo)):
    return _summary(repo, _owned(repo, qid, p))


@router.get("/{qid}/items")
def items(qid: str, state: str | None = None, p: CallerPrincipal = Depends(current_principal),
          repo: Repository = Depends(get_repo)):
    _owned(repo, qid, p)
    where = {"questionnaire_id": qid}
    if state:
        where["state"] = state
    rows = repo.list("question_items", where, order="ordinal asc", limit=5000)
    cache = ViewCache(repo)
    return {"items": [item_view(r, cache) for r in rows]}


@router.get("/{qid}/quarantine")
def quarantine(qid: str, p: CallerPrincipal = Depends(current_principal), repo: Repository = Depends(get_repo)):
    _owned(repo, qid, p)
    rows = repo.list("question_items", {"questionnaire_id": qid, "state": State.QUARANTINED}, limit=5000)
    from constat.intake.quarantine import CUSTOMER_NOTE
    cache = ViewCache(repo)
    return {"items": [item_view(r, cache) for r in rows], "customer_note": CUSTOMER_NOTE}


@router.get("/{qid}/export")
def export(qid: str, p: CallerPrincipal = Depends(current_principal), repo: Repository = Depends(get_repo)):
    q = _owned(repo, qid, p)
    qdir = _UPLOAD_DIR / p.tenant / qid
    rows = repo.list("question_items", {"questionnaire_id": qid}, order="ordinal asc", limit=5000)
    answers: dict[int, tuple[str, str]] = {}
    for r in rows:
        resp = r.final_answer if r.state == State.SENT else (
            r.final_answer or "" if r.state == State.APPROVED else "")
        notes = {State.SENT: "Sent", State.APPROVED: "Approved, not yet sent",
                 State.REVIEW: "Draft awaiting review", State.HELD: f"Held: {r.route or ''}",
                 State.REFUSED: f"Refused: {', '.join(r.flags)}", State.QUARANTINED: "Quarantined"}.get(r.state, r.state.value)
        if r.row is not None:
            answers[r.row] = (resp or "", notes)
    if q.source_kind == "xlsx" and qid in _LAYOUTS:
        out = qdir / f"{Path(q.filename).stem}__DELIVERED.xlsx"
        parsers.write_xlsx(qdir / "upload.xlsx", out, parsers.Layout(**_LAYOUTS[qid]), answers)
        return FileResponse(out, filename=out.name,
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    # csv and docx: a csv of answers, since there is no in-place write-back
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ordinal", "question", "state", "answer", "notes"])
    for r in rows:
        w.writerow([r.ordinal, r.text, r.state.value, r.final_answer or "", ", ".join(r.flags)])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{Path(q.filename).stem}__answers.csv"'})


@router.get("/{qid}/events")
async def events(qid: str, since: str = "", p: CallerPrincipal = Depends(current_principal),
                 repo: Repository = Depends(get_repo)):
    """Server-sent events: item.state as items change, questionnaire.done at
    the end. `?since=<updated_at>` returns only changes after that time."""
    _owned(repo, qid, p)

    async def gen():
        last = since
        idle = 0
        while idle < 600:          # five minutes at 0.5 s
            rows = repo.list("question_items", {"questionnaire_id": qid}, order="updated_at asc", limit=5000)
            changed = [r for r in rows if r.updated_at > last]
            for r in changed:
                yield f"event: item.state\ndata: {json.dumps({'id': r.id, 'ordinal': r.ordinal, 'state': r.state.value, 'difficulty': r.difficulty, 'updated_at': r.updated_at})}\n\n"
                last = max(last, r.updated_at)
            q = repo.get("questionnaires", qid)
            if q.status == "done" or q.status.startswith("error"):
                counts = _summary(repo, q)["counts"]
                yield f"event: questionnaire.done\ndata: {json.dumps({'status': q.status, 'counts': counts})}\n\n"
                return
            idle = 0 if changed else idle + 1
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
