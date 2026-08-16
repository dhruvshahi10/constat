"""Global run queue: one worker thread, DB-backed state, boot recovery.

One worker is a feature, not a limitation: it is what makes GeminiDrafter's
per-request pacing globally true against the free-tier rate limit. That makes
the worker a single point of failure, so three invariants are enforced here:

1. The loop never dies. Anything a job raises is logged and stepped over.
2. Exactly one worker exists. ``recover_and_start()`` is idempotent.
3. No job owns the worker forever. A run past ``RUN_BUDGET_S`` is failed and
   the queue moves on.

Errors are two-faced on purpose: ``runs.error`` holds a short stable sentence
we are happy to show a stranger, ``runs.error_detail`` holds the traceback-ish
truth and is never returned by ``status()``.
"""
from __future__ import annotations

import json
import queue
import secrets
import sys
import threading
import time
import traceback
from datetime import date
from pathlib import Path

from ..pipeline import run as pipeline_run
from ..qgen import build_questionnaire_workbook
from ..report import write_report
from . import config, db, limits
from .demo_questions import DEMO_QUESTIONS

_embedder = None

# -- user-facing error strings. status() will return nothing else. ------------
ERROR_FAILED = ("This run could not be completed (code RUN-FAILED). No answers "
                "were delivered and your documents are unchanged. Try again, or "
                "contact us if it keeps happening.")
ERROR_TIMEOUT = ("This run ran past its time budget and was stopped (code "
                 "RUN-TIMEOUT). Try again, or remove a few documents first.")
ERROR_INTERRUPTED = "interrupted by restart"
SAFE_ERRORS = frozenset({ERROR_FAILED, ERROR_TIMEOUT, ERROR_INTERRUPTED})


def _safe_error(raw: str | None) -> str | None:
    """Never let a stored string reach a client unless we minted it ourselves."""
    if not raw:
        return None
    return raw if raw in SAFE_ERRORS else ERROR_FAILED


def get_embedder():
    """Loaded once per process; production model if present, ngram floor else."""
    global _embedder
    if _embedder is None:
        from ..semantic import best_embedder
        _embedder = best_embedder()
    return _embedder


def make_retriever(slug: str):
    """Fresh per-tenant semantic index for this run; lexical None on failure.

    Rebuilding before each run (rather than at upload) keeps exactly one code
    path and guarantees the index is never stale; the corpus is small enough
    that the build is cheap at demo scale.
    """
    try:
        from ..evidence import EvidenceStore
        from ..semantic import SemanticRetriever, build_index
        store = EvidenceStore(slug, config.evidence_root(slug))
        index_dir = config.tenant_dir(slug) / "index"
        emb = get_embedder()
        build_index(store, index_dir, emb)
        return SemanticRetriever(store, index_dir, emb), emb.name
    except Exception as exc:  # noqa: BLE001 — retrieval quality never blocks a run
        sys.stderr.write(f"[runqueue] semantic unavailable for {slug}: "
                         f"{type(exc).__name__}: {exc}; using lexical\n")
        return None, "lexical-fallback"

_q: "queue.Queue[tuple[str, str]]" = queue.Queue()
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()
_orphans: list[threading.Thread] = []
_STOP = ("__stop__", "")   # sentinel: the only thing that ends the loop


class QueueError(ValueError):
    """message safe to show the requester."""


def worker_alive() -> bool:
    """True only if the single run worker exists and is still running."""
    w = _worker
    return bool(w is not None and w.is_alive())


def enqueue(slug: str, org: str, drafter: str) -> str:
    """Reserve a run slot and create the row in one atomic transaction.

    Quota, global queue depth and the INSERT are three parts of one decision;
    splitting them across transactions is how eight threads got eight runs out
    of a quota of three.
    """
    run_id = "run_" + secrets.token_hex(6)
    with db.immediate() as conn:
        quota = conn.execute(
            "SELECT run_quota FROM tenants WHERE slug=? AND status='active'",
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
        conn.execute(
            "INSERT INTO runs(id, tenant, status, drafter, question_count, "
            "queued_at, current_q, total_q) VALUES(?,?,'queued',?,?,?,0,?)",
            (run_id, slug, drafter, len(DEMO_QUESTIONS), db.now(), len(DEMO_QUESTIONS)))
    _q.put((run_id, org))
    return run_id


def status(slug: str, run_id: str) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=? AND tenant=?",
                           (run_id, slug)).fetchone()
        if row is None:
            return {"error": "run not found"}
        out = {"id": row["id"], "status": row["status"], "drafter": row["drafter"],
               "current_q": row["current_q"] or 0,
               "total_q": row["total_q"] or row["question_count"] or 0}
        if row["status"] == "queued":
            out["position"] = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE status='running' OR "
                "(status='queued' AND queued_at<?)", (row["queued_at"],)).fetchone()[0]
        if row["metrics_json"]:
            out["metrics"] = json.loads(row["metrics_json"])
        if row["status"] == "done":
            # only advertise what is still on disk: prune_run_dirs keeps the
            # newest few, so an older run's downloads would otherwise 404
            d = Path(row["dir"]) if row["dir"] else None
            names = ["run_report.html", "contracts.json", "audit_log.jsonl",
                     "metrics.json", f"{d.name}__DELIVERED.xlsx" if d else ""]
            out["files"] = ([n for n in names if n and (d / n).is_file()]
                            if d and d.is_dir() else [])
            out["pruned"] = not out["files"]
        safe = _safe_error(row["error"])
        if safe:
            # error_detail is deliberately not exposed: it carries absolute
            # paths, sqlite internals and upstream URLs.
            out["error"] = safe
        return out


def _set_progress(run_id: str, done: int, total: int) -> None:
    """Best-effort per-question progress. Never allowed to fail a run."""
    try:
        with db.connect() as conn:
            # status guard: an orphaned run whose budget expired must not
            # keep writing progress onto a row that is already terminal, or the
            # UI shows "8 of 8 complete" beside a timeout error
            conn.execute("UPDATE runs SET current_q=?, total_q=? "
                         "WHERE id=? AND status='running'",
                         (done, total, run_id))
    except Exception:  # noqa: BLE001 — progress is cosmetic
        pass


def _fail(run_id: str, message: str, detail: str) -> None:
    """Mark a still-running run failed. No-op if something else finished it."""
    try:
        with db.connect() as conn:
            conn.execute(
                "UPDATE runs SET status='error', finished_at=?, error=?, "
                "error_detail=? WHERE id=? AND status='running'",
                (db.now(), message, detail[:4000], run_id))
    except Exception:  # noqa: BLE001 — the loop must survive even this
        sys.stderr.write(f"[runqueue] could not record failure for {run_id}:\n"
                         f"{traceback.format_exc()}\n")


def _pipeline_job(run_id: str, slug: str, org: str, drafter: str, out_dir: Path,
                  aborted: threading.Event) -> None:
    """The actual work. Runs on its own thread so the budget can be enforced."""
    try:
        qnr = build_questionnaire_workbook(DEMO_QUESTIONS, out_dir / f"{run_id}.xlsx", org)
        retriever, retrieval_mode = make_retriever(slug)
        res = pipeline_run(qnr, tenant=slug, evidence_root=config.evidence_root(slug),
                           out_dir=out_dir, drafter_kind=drafter, today=date.today(),
                           approval_mode="human", retriever=retriever,
                           progress=lambda done, total: _set_progress(run_id, done, total),
                           # the budget has to stop WORK, not just stop recording
                           # it: an abandoned run still spends the shared
                           # provider rate limit, and N orphans multiply it by N
                           abort=aborted)
        res.metrics["retrieval"] = retrieval_mode
        (out_dir / "metrics.json").write_text(json.dumps(res.metrics, indent=2),
                                              encoding="utf-8")
        write_report(res, date.today())
        if aborted.is_set():
            # we lost the race with the budget; the run is already marked errored
            # and telling the user it succeeded now would be a lie
            sys.stderr.write(f"[runqueue] {run_id} finished after its budget expired; "
                             "result discarded\n")
            return
        with db.connect() as conn:
            conn.execute(
                "UPDATE runs SET status='done', finished_at=?, metrics_json=?, dir=?, "
                "current_q=total_q WHERE id=? AND status='running'",
                (db.now(), json.dumps(res.metrics), str(out_dir), run_id))
    except Exception as exc:  # noqa: BLE001 — worker must survive anything
        detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        sys.stderr.write(f"[runqueue] {run_id} failed: {detail}\n")
        if not aborted.is_set():
            _fail(run_id, ERROR_FAILED, detail)


def _execute(run_id: str, org: str) -> None:
    """Own one job end to end. Never raises; the loop's survival depends on it."""
    try:
        with db.connect() as conn:
            row = conn.execute("SELECT tenant, drafter FROM runs WHERE id=? AND "
                               "status='queued'", (run_id,)).fetchone()
            if row is None:
                return
            slug, drafter = row["tenant"], row["drafter"]
            conn.execute("UPDATE runs SET status='running', started_at=?, current_q=0, "
                         "total_q=? WHERE id=?",
                         (db.now(), len(DEMO_QUESTIONS), run_id))
    except Exception:  # noqa: BLE001 — a locked DB must not kill the worker
        sys.stderr.write(f"[runqueue] could not start {run_id}:\n"
                         f"{traceback.format_exc()}\n")
        return

    out_dir = config.runs_dir(slug) / run_id
    aborted = threading.Event()
    job = threading.Thread(target=_pipeline_job, name=f"run-{run_id}", daemon=True,
                           args=(run_id, slug, org, drafter, out_dir, aborted))
    job.start()
    job.join(timeout=config.RUN_BUDGET_S)
    if job.is_alive():
        aborted.set()
        _fail(run_id, ERROR_TIMEOUT,
              f"wall-clock budget of {config.RUN_BUDGET_S}s exceeded")
        sys.stderr.write(f"[runqueue] {run_id} exceeded {config.RUN_BUDGET_S}s budget; "
                         "abandoning it and moving on\n")
        # Python cannot kill a thread. Give the straggler a short grace period
        # so we do not run two pipelines against the same upstream rate limit,
        # then let it finish on its own (its result is discarded).
        job.join(timeout=config.ORPHAN_GRACE_S)
        if job.is_alive():
            _orphans.append(job)
    _orphans[:] = [t for t in _orphans if t.is_alive()]
    try:
        limits.prune_run_dirs(slug)
    except Exception:  # noqa: BLE001 — housekeeping never fails a run
        sys.stderr.write(f"[runqueue] prune failed for {slug}:\n"
                         f"{traceback.format_exc()}\n")


def _loop() -> None:
    """The one thing that must never stop running."""
    while True:
        try:
            item = _q.get()
        except Exception:  # noqa: BLE001 — defensive; Queue.get does not raise
            sys.stderr.write(f"[runqueue] queue get failed:\n{traceback.format_exc()}\n")
            time.sleep(1)
            continue
        if item is _STOP:
            _q.task_done()
            return
        run_id, org = item
        try:
            _execute(run_id, org)
        except Exception:  # noqa: BLE001 — one bad job must not end the worker
            sys.stderr.write(f"[runqueue] worker survived a fatal job error on "
                             f"{run_id}:\n{traceback.format_exc()}\n")
        finally:
            try:
                _q.task_done()
            except Exception:  # noqa: BLE001
                pass


def recover_and_start() -> None:
    """Boot: interrupted running -> error; queued -> requeued in order.

    Idempotent. Two workers would silently double our request rate against the
    upstream free tier, so a second call with a live worker is a no-op.
    """
    global _worker
    with _worker_lock:
        if worker_alive():
            return
        with db.connect() as conn:
            conn.execute("UPDATE runs SET status='error', finished_at=?, error=? "
                         "WHERE status='running'", (db.now(), ERROR_INTERRUPTED))
            rows = conn.execute(
                "SELECT r.id, t.org FROM runs r JOIN tenants t ON t.slug=r.tenant "
                "WHERE r.status='queued' ORDER BY r.queued_at").fetchall()
        for row in rows:
            _q.put((row["id"], row["org"]))
        _worker = threading.Thread(target=_loop, daemon=True, name="run-worker")
        _worker.start()


def stop_worker(timeout: float = 5.0) -> bool:
    """Ask the worker to finish the current job and exit. Returns True if it did.

    Used by tests and available for a graceful shutdown; the process never
    needs it in normal operation because the thread is a daemon.
    """
    global _worker
    with _worker_lock:
        w = _worker
        if w is None or not w.is_alive():
            _worker = None
            return True
        _q.put(_STOP)
        w.join(timeout=timeout)
        alive = w.is_alive()
        if not alive:
            _worker = None
        return not alive
