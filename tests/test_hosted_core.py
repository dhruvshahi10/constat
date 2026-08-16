"""Wave 0 evals: pipeline surgery invariants for hosted mode.

The constitution (test_gates.py) is untouched; these extend it.
"""
from datetime import date
from pathlib import Path

import json
import pytest

from pramana.models import Draft, QState
from pramana.pipeline import AuditLog, run
from pramana.qgen import build_questionnaire_workbook
from pramana.server.demo_questions import DEMO_QUESTIONS

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 8, 12)


@pytest.fixture(scope="module")
def human_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("hosted")
    qnr = build_questionnaire_workbook(DEMO_QUESTIONS, out / "hosted_demo.xlsx", "Acme Corp")
    return run(qnr, tenant="acme", evidence_root=ROOT / "data" / "evidence",
               out_dir=out / "run", drafter_kind="mock", today=TODAY,
               approval_mode="human")


# --- human mode: nothing self-approves --------------------------------------
def test_human_mode_delivers_nothing(human_run):
    assert all(q.state != QState.DELIVERED for q in human_run.questions)
    assert human_run.metrics["auto_approved_delivered"] == 0
    log = (human_run.out_dir / "audit_log.jsonl").read_text()
    assert "SIMULATED_DEMO_APPROVAL" not in log
    assert "APPROVED" not in log


def test_human_mode_still_zero_unsupported(human_run):
    assert human_run.metrics["unsupported_material_claims"] == 0
    assert human_run.metrics["audit_chain_valid"] is True


def test_state_json_written(human_run):
    state = json.loads((human_run.out_dir / "state.json").read_text())
    assert state["approval_mode"] == "human"
    assert len(state["questions"]) == len(DEMO_QUESTIONS)
    assert {q["question_id"] for q in state["questions"]} == \
        {qid for qid, _, _ in DEMO_QUESTIONS}


# --- generated workbook exercises the certified ingest path ------------------
def test_qgen_workbook_roundtrip(human_run):
    # every demo question ingested, none dropped, rows preserved
    ids = [q.question_id for q in human_run.questions]
    assert ids == [qid for qid, _, _ in DEMO_QUESTIONS]
    assert all(q.row >= 4 for q in human_run.questions)


def test_traps_still_fire_on_demo_set(human_run):
    d = {q.question_id: human_run.drafts[q.question_id] for q in human_run.questions}
    assert d["H-10"].route == "LEGAL"                       # legal pre-gate
    assert d["H-09"].abstained                              # cert never inferred
    assert d["H-05"].abstained                              # deletion contradiction
    assert any(f.startswith("CONTRADICTION") for f in d["H-05"].gate_flags)


# --- AuditLog.resume ---------------------------------------------------------
def test_resume_continues_chain(tmp_path):
    p = tmp_path / "log.jsonl"
    log = AuditLog(p)
    log.append("system", "A", "s1")
    log.append("system", "B", "s2")
    resumed = AuditLog.resume(p)
    resumed.append("Priya N.", "APPROVED", "H-01", {"note": "checked"})
    assert AuditLog.verify_chain(p) is True
    lines = p.read_text().splitlines()
    assert len(lines) == 3
    assert json.loads(lines[2])["actor"] == "Priya N."
    assert json.loads(lines[2])["prev_hash"] == json.loads(lines[1])["hash"]


def test_resume_refuses_broken_chain(tmp_path):
    p = tmp_path / "log.jsonl"
    log = AuditLog(p)
    log.append("system", "A", "s1")
    log.append("system", "B", "s2")
    lines = p.read_text().splitlines()
    tampered = json.loads(lines[0])
    tampered["action"] = "EDITED"
    lines[0] = json.dumps(tampered, ensure_ascii=False)
    p.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError):
        AuditLog.resume(p)


# --- Draft.from_contract -----------------------------------------------------
def test_contract_roundtrip(human_run):
    for qid, d in human_run.drafts.items():
        back = Draft.from_contract(d.to_contract())
        assert back == d, qid


def test_unknown_approval_mode_rejected(tmp_path):
    with pytest.raises(ValueError):
        run(ROOT / "data" / "questionnaires" / "acme_security_questionnaire.xlsx",
            tenant="acme", evidence_root=ROOT / "data" / "evidence",
            out_dir=tmp_path, approval_mode="yolo")
