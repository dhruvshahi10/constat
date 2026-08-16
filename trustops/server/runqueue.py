"""Global run queue: one worker thread, DB-backed state, boot recovery.

One worker is a feature, not a limitation: it is what makes GeminiDrafter's
per-request pacing globally true against the free-tier rate limit.
"""
from __future__ import annotations

import json
import queue
import secrets
import sys
import threading
import traceback
from datetime import date
from pathlib import Path

from ..pipeline import run as pipeline_run
from ..qgen import build_questionnaire_workbook
from ..report import write_report
from . import config, db
from .demo_questions import DEMO_QUESTIONS

_q: "queue.Queue[str]" = queue.Queue()
_worker: threading.Thread | None = None


class QueueError(ValueError):
    """message safe to show the requester."""


def enqueue(slug: str, org: str, drafter: str) -> str:
    with db.connect() as conn:
        quota = conn.execute("SELECT run_quota FROM tenants WHERE slug=? AND status='active'",
                             (slug,)).fetchone()
        if quota is None:
            raise QueueError("Workspace not found or expired.")
        used = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE tenant=? AND status IN "
            "('queued','running','done')", (slug,)).fetchone()[0]
        if used >= quota["run_quota"]:
            raise QueueError("Run quota reached for this workspace. Book a pilot "
                             "for unlimited runs.")
        depth = conn.execute("SELECT COUNT(*) FROM runs WHERE status IN "
                             "('queued','running')").fetchone()[0]
        if depth >= config.GLOBAL_QUEUE_DEPTH:
            raise QueueError("The demo queue is full right now. Try again in an hour.")
        run_id = "run_" + secrets.token_hex(6)
        conn.execute(
            "INSERT INTO runs(id, tenant, status, drafter, question_count, queued_at) "
            "VALUES(?,?,'queued',?,?,?)",
            (run_id, slug, drafter, len(DEMO_QUESTIONS), db.now()))
    _q.put((run_id, org))
    return run_id


def status(slug: str, run_id: str) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=? AND tenant=?",
                           (run_id, slug)).fetchone()
        if row is None:
            return {"error": "run not found"}
        out = {"id": row["id"], "status": row["status"], "drafter": row["drafter"]}
        if row["status"] == "queued":
            out["position"] = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE status='running' OR "
                "(status='queued' AND queued_at<?)", (row["queued_at"],)).fetchone()[0]
        if row["metrics_json"]:
            out["metrics"] = json.loads(row["metrics_json"])
        if row["status"] == "done":
            out["files"] = ["run_report.html", "contracts.json", "audit_log.jsonl",
                            "metrics.json",
                            f"{Path(row['dir']).name}__DELIVERED.xlsx"]
        if row["error"]:
            out["error"] = row["error"]
        return out


def _execute(run_id: str, org: str) -> None:
    with db.connect() as conn:
        row = conn.execute("SELECT tenant, drafter FROM runs WHERE id=?",
                           (run_id,)).fetchone()
    if row is None:
        return
    slug, drafter = row["tenant"], row["drafter"]
    out_dir = config.runs_dir(slug) / run_id
    with db.connect() as conn:
        conn.execute("UPDATE runs SET status='running', started_at=? WHERE id=?",
                     (db.now(), run_id))
    try:
        qnr = build_questionnaire_workbook(DEMO_QUESTIONS, out_dir / f"{run_id}.xlsx", org)
        res = pipeline_run(qnr, tenant=slug, evidence_root=config.evidence_root(slug),
                           out_dir=out_dir, drafter_kind=drafter, today=date.today(),
                           approval_mode="human")
        write_report(res, date.today())
        with db.connect() as conn:
            conn.execute(
                "UPDATE runs SET status='done', finished_at=?, metrics_json=?, dir=? "
                "WHERE id=?",
                (db.now(), json.dumps(res.metrics), str(out_dir), run_id))
    except Exception as exc:  # noqa: BLE001 — worker must survive anything
        sys.stderr.write(f"[runqueue] {run_id} failed: {traceback.format_exc()}\n")
        with db.connect() as conn:
            conn.execute("UPDATE runs SET status='error', finished_at=?, error=? WHERE id=?",
                         (db.now(), f"{type(exc).__name__}: {exc}", run_id))


def _loop() -> None:
    while True:
        run_id, org = _q.get()
        try:
            _execute(run_id, org)
        finally:
            _q.task_done()


def recover_and_start() -> None:
    """Boot: interrupted running -> error; queued -> requeued in order."""
    global _worker
    with db.connect() as conn:
        conn.execute("UPDATE runs SET status='error', error='interrupted by restart' "
                     "WHERE status='running'")
        rows = conn.execute(
            "SELECT r.id, t.org FROM runs r JOIN tenants t ON t.slug=r.tenant "
            "WHERE r.status='queued' ORDER BY r.queued_at").fetchall()
    for row in rows:
        _q.put((row["id"], row["org"]))
    _worker = threading.Thread(target=_loop, daemon=True, name="run-worker")
    _worker.start()
