"""Abuse limits: signup rate, run quotas, tenant expiry sweep."""
from __future__ import annotations

import shutil
import threading
import time
from datetime import datetime, timedelta, timezone

from . import config, db


def signup_allowed(ip: str) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with db.connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM signup_events WHERE ip=? AND created_at>?",
            (ip, cutoff)).fetchone()[0]
    return n < config.SIGNUPS_PER_IP_PER_DAY


def record_signup(ip: str) -> None:
    with db.connect() as conn:
        conn.execute("INSERT INTO signup_events(ip, created_at) VALUES(?,?)",
                     (ip, db.now()))


def runs_remaining(slug: str) -> int:
    with db.connect() as conn:
        row = conn.execute("SELECT run_quota FROM tenants WHERE slug=?", (slug,)).fetchone()
        if row is None:
            return 0
        used = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE tenant=? AND status IN "
            "('queued','running','done')", (slug,)).fetchone()[0]
    return max(0, row["run_quota"] - used)


def doc_count(slug: str) -> int:
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM uploads WHERE tenant=?",
                            (slug,)).fetchone()[0]


def sweep_expired() -> int:
    """Hard-delete expired tenants' data; keep the row for rate-limit memory."""
    n = 0
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT slug FROM tenants WHERE status='active' AND expires_at<?",
            (db.now(),)).fetchall()
        for row in rows:
            slug = row["slug"]
            shutil.rmtree(config.tenant_dir(slug), ignore_errors=True)
            conn.execute("UPDATE tenants SET status='expired' WHERE slug=?", (slug,))
            conn.execute("DELETE FROM uploads WHERE tenant=?", (slug,))
            n += 1
    return n


def start_sweeper() -> threading.Thread:
    def loop() -> None:
        while True:
            try:
                sweep_expired()
            except Exception:  # noqa: BLE001 — sweeper must never die
                pass
            time.sleep(3600)
    t = threading.Thread(target=loop, daemon=True, name="tenant-sweeper")
    t.start()
    return t
