"""Eval (e): queue quota, FIFO position, boot recovery."""
from pathlib import Path

import pytest

from trustops.server import auth, config, db, limits, runqueue


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path / "data")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "data" / "trustops.db")
    monkeypatch.setattr(config, "TENANTS", tmp_path / "data" / "tenants")
    db.init()
    with db.connect() as conn:
        for slug in ("alpha", "beta"):
            _, th = auth.mint_token(slug)
            conn.execute(
                "INSERT INTO tenants(slug, org, email, token_hash, created_at, "
                "expires_at, run_quota) VALUES(?,?,?,?,?,?,3)",
                (slug, slug.title(), f"a@{slug}.com", th, db.now(), db.in_days(14)))
    return tmp_path


def test_quota_enforced(env):
    for _ in range(3):
        runqueue.enqueue("alpha", "Alpha", "mock")
    with pytest.raises(runqueue.QueueError, match="quota"):
        runqueue.enqueue("alpha", "Alpha", "mock")


def test_fifo_position(env):
    r1 = runqueue.enqueue("alpha", "Alpha", "mock")
    r2 = runqueue.enqueue("beta", "Beta", "mock")
    assert runqueue.status("alpha", r1)["position"] == 0
    assert runqueue.status("beta", r2)["position"] == 1


def test_cross_tenant_status_denied(env):
    r1 = runqueue.enqueue("alpha", "Alpha", "mock")
    assert runqueue.status("beta", r1) == {"error": "run not found"}


def test_boot_recovery(env):
    r1 = runqueue.enqueue("alpha", "Alpha", "mock")
    with db.connect() as conn:
        conn.execute("UPDATE runs SET status='running' WHERE id=?", (r1,))
    r2 = runqueue.enqueue("beta", "Beta", "mock")
    # drain the in-memory queue to simulate a dead process
    while not runqueue._q.empty():
        runqueue._q.get_nowait()

    with db.connect() as conn:
        conn.execute("UPDATE runs SET status='error', error='interrupted by restart' "
                     "WHERE status='running'")
        rows = conn.execute("SELECT id FROM runs WHERE status='queued' "
                            "ORDER BY queued_at").fetchall()
    assert runqueue.status("alpha", r1)["error"] == "interrupted by restart"
    assert [r["id"] for r in rows] == [r2]


def test_unknown_tenant_rejected(env):
    with pytest.raises(runqueue.QueueError, match="not found"):
        runqueue.enqueue("ghost", "Ghost", "mock")


def test_signup_rate_limit(env):
    for _ in range(config.SIGNUPS_PER_IP_PER_DAY):
        assert limits.signup_allowed("1.2.3.4")
        limits.record_signup("1.2.3.4")
    assert limits.signup_allowed("1.2.3.4") is False
    assert limits.signup_allowed("5.6.7.8") is True
