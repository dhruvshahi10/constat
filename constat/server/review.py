"""Named-reviewer approval over a completed hosted run.

Invariants enforced here, not in the UI:
  - only GRC_REVIEW questions can be approved (an EXCEPTION has no surviving
    citations; citation-or-abstain means no approval path may release it)
  - reviewer name and note are mandatory
  - every action appends to the run's existing hash chain via AuditLog.resume,
    which refuses tampered chains
  - DELIVERED.xlsx and the report are regenerated after every action
"""
from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path

from ..export import export_answers, ingest_questionnaire
from ..models import Draft, QState
from ..pipeline import AuditLog, RunResult
from ..report import write_report
from . import db

_lock = threading.Lock()


class ReviewError(ValueError):
    """message safe to show the reviewer."""


def _load(run_dir: Path):
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    contracts = json.loads((run_dir / "contracts.json").read_text(encoding="utf-8"))
    drafts = {qid: Draft.from_contract(c) for qid, c in contracts.items()}
    questions = ingest_questionnaire(run_dir / state["questionnaire"])
    states = {q["question_id"]: q["state"] for q in state["questions"]}
    for q in questions:
        q.state = QState(states[q.question_id])
    return state, questions, drafts


def _persist(run_dir: Path, state: dict, questions, drafts) -> None:
    state["questions"] = [{"question_id": q.question_id, "row": q.row,
                           "domain": q.domain, "text": q.text, "state": q.state.value}
                          for q in questions]
    (run_dir / "state.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    src = run_dir / state["questionnaire"]
    delivered = run_dir / f"{src.stem}__DELIVERED.xlsx"
    export_answers(src, delivered, questions, drafts)

    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    metrics["auto_approved_delivered"] = sum(
        1 for q in questions if q.state == QState.DELIVERED)
    metrics["awaiting_human_review"] = sum(
        1 for q in questions if q.state == QState.GRC_REVIEW)
    metrics["audit_chain_valid"] = AuditLog.verify_chain(run_dir / "audit_log.jsonl")
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    res = RunResult(tenant=state["tenant"], questions=questions, drafts=drafts,
                    metrics=metrics, out_dir=run_dir, delivered_xlsx=delivered,
                    audit_path=run_dir / "audit_log.jsonl")
    write_report(res, date.fromisoformat(state["run_date"]))


def queue_items(run_dir: Path) -> list[dict]:
    """Questions awaiting a decision, with enough context to decide."""
    state, questions, drafts = _load(run_dir)
    items = []
    for q in questions:
        if q.state not in (QState.GRC_REVIEW, QState.EXCEPTION):
            continue
        d = drafts[q.question_id]
        items.append({
            "question_id": q.question_id, "domain": q.domain, "text": q.text,
            "state": q.state.value, "answer": d.answer,
            "citations": [f"{c.source_id} v{c.version} {c.location}" for c in d.citations],
            "gaps": d.gaps, "route": d.route, "gate_flags": d.gate_flags,
            "coverage": d.evidence_coverage.value,
        })
    return items


def act(run_dir: Path, question_id: str, action: str, reviewer: str, note: str) -> dict:
    reviewer, note = reviewer.strip(), note.strip()
    if not reviewer or not note:
        raise ReviewError("Reviewer name and note are both required.")
    if action not in ("approve", "reject", "route"):
        raise ReviewError("Action must be approve, reject, or route.")

    with _lock:
        state, questions, drafts = _load(run_dir)
        q = next((x for x in questions if x.question_id == question_id), None)
        if q is None:
            raise ReviewError(f"Unknown question {question_id}.")
        d = drafts[question_id]

        if action == "approve":
            if q.state != QState.GRC_REVIEW:
                raise ReviewError(
                    "Only cited drafts awaiting review can be approved. An exception "
                    "has no gate-surviving citation and can never be released.")
            q.state = QState.DELIVERED
            audit_action = "APPROVED"
        elif action == "reject":
            if q.state != QState.GRC_REVIEW:
                raise ReviewError("Only cited drafts awaiting review can be rejected.")
            q.state = QState.EXCEPTION
            d.answer = None
            d.abstained = True
            d.requires_human = True
            d.route = d.route or "SME"
            d.gaps.append(f"Rejected by reviewer {reviewer}: {note}")
            audit_action = "REJECTED"
        else:  # route: annotate an exception onward (no state change)
            if q.state != QState.EXCEPTION:
                raise ReviewError("Route is for exceptions.")
            d.gaps.append(f"Routed by reviewer {reviewer}: {note}")
            audit_action = "ROUTED"

        audit = AuditLog.resume(run_dir / "audit_log.jsonl")
        audit.append(reviewer, audit_action, question_id, {
            "mode": "HUMAN_REVIEW", "note": note, "identity": "self-attested",
            "citations": [f"{c.source_id}@{c.location}" for c in d.citations],
        })
        _persist(run_dir, state, questions, drafts)

        with db.connect() as conn:
            conn.execute(
                "INSERT INTO approvals(run_id, question_id, actor, action, note, ts) "
                "VALUES(?,?,?,?,?,?)",
                (run_dir.name, question_id, reviewer, audit_action, note, db.now()))

    return {"question_id": question_id, "state": q.state.value, "action": audit_action}
