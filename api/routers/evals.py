"""Model-evaluation records: the artefact customers and auditors ask for."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from constat.persist import ModelEvalRecord, Repository, ulid

from ..auth import CallerPrincipal, current_principal, require
from ..deps import get_repo

router = APIRouter(prefix="/v1/evals", tags=["evals"])


class RecordBody(BaseModel):
    model_id: str
    prompt_version: str
    golden_pass_rate: float
    dangerous_failures: int
    injection_pass_rate: float
    cost_per_questionnaire_usd: float
    p95_latency_ms: int
    artefact_json: dict = {}


@router.get("/records")
def records(_: CallerPrincipal = Depends(current_principal), repo: Repository = Depends(get_repo)):
    rows = repo.list("model_eval_records", order="run_at desc", limit=100)
    return {"records": [r.to_row() | {"artefact_json": r.artefact_json} for r in rows]}


@router.post("/records", status_code=201)
def add_record(body: RecordBody, _: CallerPrincipal = Depends(require("admin")),
               repo: Repository = Depends(get_repo)):
    rec = ModelEvalRecord(id=ulid(), **body.model_dump())
    repo.insert("model_eval_records", rec)
    return rec.to_row() | {"artefact_json": rec.artefact_json}
