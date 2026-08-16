"""Concurrency and crash-resilience evals.

Part one — every limit must be atomic, not check-then-act. Python's sqlite3
does NOT open a transaction for a bare SELECT, so a `SELECT COUNT(*)` followed
by an `INSERT` inside one `with conn:` block are in two different transactions.
Eight threads racing a quota of three used to produce eight rows. These tests
fail against the check-then-act version and pass against BEGIN IMMEDIATE.

Part two — the single run worker is the whole service's throughput. It must
survive a poisoned job, refuse to be started twice, refuse to be held forever
by one run, and never hand an internal error string to a client.

Part three — a process killed mid-write must degrade honestly. A torn audit
line is a failed verification, not an exception.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from pramana.pipeline import AuditLog
from pramana.server import auth, config, db, limits, runqueue


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path / "data")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "data" / "pramana.db")
    monkeypatch.setattr(config, "TENANTS", tmp_path / "data" / "tenants")
    db.init()
    with db.connect() as conn:
        for slug in ("alpha", "beta", "gamma", "delta"):
            _, th = auth.mint_token(slug)
            conn.execute(
                "INSERT INTO tenants(slug, org, email, token_hash, created_at, "
                "expires_at, run_quota) VALUES(?,?,?,?,?,?,3)",
                (slug, slug.title(), f"a@{slug}.com", th, db.now(), db.in_days(14)))
    # keep the worker and the in-memory dispatch queue from leaking between
    # tests (a worker left alive would eat other modules' enqueued runs)
    yield tmp_path
    runqueue.stop_worker()
    runqueue._worker = None
    while not runqueue._q.empty():
        runqueue._q.get_nowait()


def _race(fn, n: int) -> tuple[int, list[Exception]]:
    """Run fn() on n threads released simultaneously. Returns (oks, errors)."""
    barrier = threading.Barrier(n)
    oks: list[object] = []
    errs: list[Exception] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        try:
            out = fn()
        except Exception as exc:  # noqa: BLE001 — the test is the assertion
            with lock:
                errs.append(exc)
        else:
            with lock:
                oks.append(out)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "a racing thread hung"
    return len(oks), errs


def _run_rows(slug: str | None = None) -> int:
    with db.connect() as conn:
        if slug is None:
            return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM runs WHERE tenant=?",
                            (slug,)).fetchone()[0]


def test_enqueue_quota_is_atomic(env):
    """C2: 8 threads, quota 3 -> exactly 3 rows, 5 clean QueueErrors."""
    oks, errs = _race(lambda: runqueue.enqueue("alpha", "Alpha", "mock"), 8)
    assert _run_rows("alpha") == 3, "run quota was oversubscribed by the race"
    assert oks == 3
    assert len(errs) == 5
    assert all(isinstance(e, runqueue.QueueError) for e in errs), errs
    assert all("quota" in str(e) for e in errs), errs


def test_enqueue_global_depth_is_atomic(env, monkeypatch):
    """The global queue-depth ceiling must also survive a stampede."""
    monkeypatch.setattr(config, "GLOBAL_QUEUE_DEPTH", 2)
    slugs = ["alpha", "beta", "gamma", "delta"] * 2
    counter = iter(slugs)
    lock = threading.Lock()

    def one() -> str:
        with lock:
            slug = next(counter)
        return runqueue.enqueue(slug, slug.title(), "mock")

    oks, errs = _race(one, 8)
    assert _run_rows() == 2, "global queue depth was oversubscribed by the race"
    assert oks == 2
    assert all(isinstance(e, runqueue.QueueError) for e in errs), errs


def test_signup_cap_is_atomic(env, monkeypatch):
    """C3 backstop: the per-IP daily signup cap must not be racy either."""
    monkeypatch.setattr(config, "SIGNUPS_PER_IP_PER_DAY", 3)
    monkeypatch.setattr(config, "SIGNUPS_PER_DAY_GLOBAL", 1000)

    def one() -> None:
        with db.immediate() as conn:
            limits.claim_signup(conn, "9.9.9.9")

    oks, errs = _race(one, 8)
    with db.connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM signup_events").fetchone()[0]
    assert n == 3, "signup cap was oversubscribed by the race"
    assert oks == 3
    assert all(isinstance(e, limits.LimitError) for e in errs), errs


def test_doc_limit_is_atomic(env, monkeypatch):
    """MAX_DOCS_PER_TENANT must be claimed under the same write lock."""
    monkeypatch.setattr(config, "MAX_DOCS_PER_TENANT", 3)
    counter = iter(range(100))
    lock = threading.Lock()

    def one() -> None:
        with lock:
            i = next(counter)
        with db.immediate() as conn:
            limits.claim_upload_slot(conn, "alpha", nbytes=10)
            conn.execute(
                "INSERT INTO uploads(tenant, source_id, filename, sha256, bytes, "
                "approved, created_at) VALUES(?,?,?,?,?,0,?)",
                ("alpha", f"SID-{i}", f"f{i}.md", f"sha{i}", 10, db.now()))

    oks, errs = _race(one, 8)
    with db.connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM uploads WHERE tenant='alpha'").fetchone()[0]
    assert n == 3, "document limit was oversubscribed by the race"
    assert oks == 3
    assert all(isinstance(e, limits.LimitError) for e in errs), errs


# ---------------------------------------------------------------------------
# C1 — the worker must never die, and must never be duplicated
# ---------------------------------------------------------------------------
def test_worker_survives_a_poisoned_job(env, monkeypatch):
    """One `database is locked` used to kill the worker for the process's life."""
    seen: list[str] = []
    gate = threading.Event()

    def explode(run_id: str, org: str) -> None:
        seen.append(run_id)
        if len(seen) >= 2:
            gate.set()
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(runqueue, "_execute", explode)
    runqueue.recover_and_start()
    try:
        assert runqueue.worker_alive()
        runqueue.enqueue("alpha", "Alpha", "mock")
        runqueue.enqueue("beta", "Beta", "mock")
        assert gate.wait(timeout=10), f"worker stopped after {len(seen)} job(s)"
        assert len(seen) == 2
        assert runqueue.worker_alive(), "worker died on the first exception"
    finally:
        runqueue.stop_worker()


def test_recover_and_start_is_idempotent(env):
    """Two workers would silently double our upstream request rate."""
    runqueue.recover_and_start()
    first = runqueue._worker
    try:
        runqueue.recover_and_start()
        runqueue.recover_and_start()
        assert runqueue._worker is first
        assert sum(1 for t in threading.enumerate() if t.name == "run-worker") == 1
    finally:
        runqueue.stop_worker()


def test_worker_alive_reports_a_dead_worker(env):
    runqueue._worker = None
    assert runqueue.worker_alive() is False
    runqueue.recover_and_start()
    assert runqueue.worker_alive() is True
    assert runqueue.stop_worker() is True
    assert runqueue.worker_alive() is False


# ---------------------------------------------------------------------------
# H7 — no single run may own the worker forever
# ---------------------------------------------------------------------------
def test_run_budget_stops_a_hung_run(env, monkeypatch):
    monkeypatch.setattr(config, "RUN_BUDGET_S", 1)
    monkeypatch.setattr(config, "ORPHAN_GRACE_S", 0)
    monkeypatch.setattr(runqueue, "make_retriever", lambda slug: (None, "test"))
    monkeypatch.setattr(runqueue, "build_questionnaire_workbook",
                        lambda questions, path, org: Path(path))
    entered = threading.Event()
    release = threading.Event()

    def hang(*a, **k):
        entered.set()
        release.wait(timeout=20)
        raise AssertionError("this result must never be recorded")

    monkeypatch.setattr(runqueue, "pipeline_run", hang)

    run_id = runqueue.enqueue("alpha", "Alpha", "mock")
    runqueue._q.get_nowait()                       # drive _execute directly
    t0 = time.monotonic()
    runqueue._execute(run_id, "Alpha")
    elapsed = time.monotonic() - t0

    assert elapsed < 10, "the budget did not release the worker"
    st = runqueue.status("alpha", run_id)
    assert st["status"] == "error"
    assert st["error"] == runqueue.ERROR_TIMEOUT

    # the abandoned job must not be able to resurrect the run afterwards
    release.set()
    time.sleep(0.3)
    assert runqueue.status("alpha", run_id)["status"] == "error"


# ---------------------------------------------------------------------------
# H5 — internal detail is stored, never served
# ---------------------------------------------------------------------------
def test_status_never_returns_internal_detail(env):
    run_id = runqueue.enqueue("alpha", "Alpha", "mock")
    leak = ("OperationalError: /srv/data-hosted/pramana.db is locked; "
            "https://generativelanguage.googleapis.com/v1beta/models?key=AIza")
    with db.connect() as conn:
        conn.execute("UPDATE runs SET status='error', error=?, error_detail=? WHERE id=?",
                     (leak, leak, run_id))
    out = runqueue.status("alpha", run_id)
    assert out["error"] == runqueue.ERROR_FAILED
    assert "error_detail" not in out
    for needle in ("/srv/", "OperationalError", "googleapis", "AIza"):
        assert needle not in json.dumps(out), needle
    # the truth is still on disk for us
    with db.connect() as conn:
        assert conn.execute("SELECT error_detail FROM runs WHERE id=?",
                            (run_id,)).fetchone()[0] == leak


def test_status_preserves_the_restart_message(env):
    run_id = runqueue.enqueue("alpha", "Alpha", "mock")
    with db.connect() as conn:
        conn.execute("UPDATE runs SET status='error', error=? WHERE id=?",
                     (runqueue.ERROR_INTERRUPTED, run_id))
    assert runqueue.status("alpha", run_id)["error"] == "interrupted by restart"


def test_status_exposes_progress(env):
    run_id = runqueue.enqueue("alpha", "Alpha", "mock")
    out = runqueue.status("alpha", run_id)
    assert out["current_q"] == 0
    assert out["total_q"] > 0
    # progress is only ever reported by the worker while the run is running,
    # which is the state the guard in _set_progress requires
    with db.connect() as conn:
        conn.execute("UPDATE runs SET status='running' WHERE id=?", (run_id,))
    runqueue._set_progress(run_id, 7, out["total_q"])
    assert runqueue.status("alpha", run_id)["current_q"] == 7


def test_progress_is_refused_on_a_terminal_run(env):
    """An orphaned run whose budget expired keeps executing until it finishes.

    Without a status guard it goes on writing progress onto a row that is
    already errored, and the UI shows "8 of 8 complete" next to a timeout.
    """
    run_id = runqueue.enqueue("alpha", "Alpha", "mock")
    with db.connect() as conn:
        conn.execute("UPDATE runs SET status='error', error=? WHERE id=?",
                     (runqueue.ERROR_TIMEOUT, run_id))
    runqueue._set_progress(run_id, 8, 8)
    out = runqueue.status("alpha", run_id)
    assert out["current_q"] == 0, "a terminal run must not accept progress writes"
    assert out["status"] == "error"


# ---------------------------------------------------------------------------
# H6 — a torn audit line must fail honestly, not explode
# ---------------------------------------------------------------------------
def test_torn_last_line_fails_verification(tmp_path):
    p = tmp_path / "audit_log.jsonl"
    log = AuditLog(p)
    log.append("system", "RECEIVED", "q.xlsx")
    log.append("system", "CLASSIFIED", "q.xlsx")
    # SIGKILL mid-append: the final record is half written
    with p.open("a", encoding="utf-8") as f:
        f.write('{"ts": "2026-08-16T00:00:00+00:00", "actor": "sys", "act')
    assert AuditLog.verify_chain(p) is False
    with pytest.raises(ValueError, match="refusing to append"):
        AuditLog.resume(p)


@pytest.mark.parametrize("garbage", [
    "not json at all",
    "[]",
    '{"no_hash": 1}',
    "null",
    '"just a string"',
])
def test_malformed_line_fails_verification(tmp_path, garbage):
    p = tmp_path / "audit_log.jsonl"
    log = AuditLog(p)
    log.append("system", "RECEIVED", "q.xlsx")
    with p.open("a", encoding="utf-8") as f:
        f.write(garbage + "\n")
    assert AuditLog.verify_chain(p) is False


def test_missing_log_is_not_a_valid_chain(tmp_path):
    assert AuditLog.verify_chain(tmp_path / "nope.jsonl") is False


def test_intact_chain_still_verifies(tmp_path):
    p = tmp_path / "audit_log.jsonl"
    log = AuditLog(p)
    for i in range(5):
        log.append("system", "STEP", f"s{i}")
    assert AuditLog.verify_chain(p) is True
    AuditLog.resume(p).append("Priya N.", "APPROVED", "H-01")
    assert AuditLog.verify_chain(p) is True
