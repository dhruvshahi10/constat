"""Abuse limits: signup rate, run quotas, disk budget, tenant expiry sweep.

Anything that decides "is there room for one more?" and then creates the thing
is a check-then-act race unless both halves run under one write lock. The
``claim_*`` functions here take an *already-immediate* connection (see
``db.immediate``) and either reserve the slot or raise ``LimitError``; the
caller does its INSERT on the same connection, inside the same transaction.
"""
from __future__ import annotations

import shutil
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, db


class LimitError(ValueError):
    """message is safe to show the requester verbatim."""


def _day_cutoff() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


# -- signup -------------------------------------------------------------------
def claim_signup(conn: sqlite3.Connection, ip: str) -> None:
    """Reserve one signup for `ip`, atomically. Raises LimitError if capped.

    Must be called on a connection inside a BEGIN IMMEDIATE transaction: the
    count and the INSERT are the two halves of one decision.
    """
    cutoff = _day_cutoff()
    per_ip = conn.execute(
        "SELECT COUNT(*) FROM signup_events WHERE ip=? AND created_at>?",
        (ip, cutoff)).fetchone()[0]
    if per_ip >= config.SIGNUPS_PER_IP_PER_DAY:
        raise LimitError("Signup limit reached from this network today.")
    # global backstop: one attacker rotating IPs still cannot mint unbounded
    # workspaces (each one costs us disk and a Gemini quota slice)
    total = conn.execute(
        "SELECT COUNT(*) FROM signup_events WHERE created_at>?", (cutoff,)).fetchone()[0]
    if total >= config.SIGNUPS_PER_DAY_GLOBAL:
        raise LimitError("Signups are paused for today. Please try again tomorrow.")
    conn.execute("INSERT INTO signup_events(ip, created_at) VALUES(?,?)", (ip, db.now()))


def signup_allowed(ip: str) -> bool:
    """Read-only view of the per-IP cap. Advisory: not a substitute for a claim."""
    with db.connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM signup_events WHERE ip=? AND created_at>?",
            (ip, _day_cutoff())).fetchone()[0]
    return n < config.SIGNUPS_PER_IP_PER_DAY


def record_signup(ip: str) -> None:
    with db.connect() as conn:
        conn.execute("INSERT INTO signup_events(ip, created_at) VALUES(?,?)",
                     (ip, db.now()))


# -- per-tenant resources -----------------------------------------------------
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


def tenant_bytes(slug: str) -> int:
    with db.connect() as conn:
        return conn.execute("SELECT COALESCE(SUM(bytes),0) FROM uploads WHERE tenant=?",
                            (slug,)).fetchone()[0]


def claim_upload_slot(conn: sqlite3.Connection, slug: str, nbytes: int) -> None:
    """Reserve one document slot and `nbytes` of budget, atomically.

    Must be called on a BEGIN IMMEDIATE connection; the caller inserts the
    uploads row on the same connection before the transaction closes.
    """
    n = conn.execute("SELECT COUNT(*) FROM uploads WHERE tenant=?", (slug,)).fetchone()[0]
    if n >= config.MAX_DOCS_PER_TENANT:
        raise LimitError(
            f"Workspace document limit ({config.MAX_DOCS_PER_TENANT}) reached.")
    used = conn.execute("SELECT COALESCE(SUM(bytes),0) FROM uploads WHERE tenant=?",
                        (slug,)).fetchone()[0]
    if used + nbytes > config.MAX_TENANT_BYTES:
        mb = config.MAX_TENANT_BYTES // (1024 * 1024)
        raise LimitError(f"Workspace storage limit ({mb} MB) reached. "
                         "Delete a document and try again.")


# -- disk ---------------------------------------------------------------------
def prune_run_dirs(slug: str, keep: int | None = None) -> int:
    """Keep the newest `keep` run output directories; delete the rest.

    Run outputs are the only unbounded writer on the disk (a workspace lives 14
    days but can produce a report set per run). The DB rows stay: `status()`
    still answers, the files just stop being downloadable.
    """
    keep = config.KEEP_RUN_DIRS if keep is None else keep
    root = config.runs_dir(slug)
    if not root.is_dir():
        return 0
    dirs = sorted((d for d in root.iterdir() if d.is_dir()),
                  key=lambda d: d.stat().st_mtime, reverse=True)
    removed = 0
    for d in dirs[keep:]:
        shutil.rmtree(d, ignore_errors=True)
        removed += 1
    return removed


def delete_upload_blob(slug: str, sha256: str, filename: str) -> bool:
    """Unlink the raw uploaded blob written alongside the synthesized .md."""
    updir = config.uploads_dir(slug)
    target = updir / f"{sha256}{Path(filename).suffix.lower()}"
    if target.is_file() and target.resolve().is_relative_to(updir.resolve()):
        target.unlink()
        return True
    # suffix drift (renamed file, odd casing): fall back to sha-prefix match
    hit = False
    if updir.is_dir():
        for p in updir.glob(f"{sha256}.*"):
            p.unlink(missing_ok=True)
            hit = True
    return hit


# -- expiry -------------------------------------------------------------------
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
        # signup_events is append-only and only ever read over a 1-day window
        conn.execute("DELETE FROM signup_events WHERE created_at<?", (db.since_days(7),))
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
