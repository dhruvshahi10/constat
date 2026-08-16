"""SQLite persistence. One connection per call site, WAL mode, single process.

Two connection helpers, and the difference matters:

* ``connect()`` — ordinary deferred connection. Fine for reads and for writes
  whose correctness does not depend on what a concurrent writer is doing.
* ``immediate()`` — context manager that takes the database write lock *before*
  the first statement runs. Every check-then-act limit (run quota, queue depth,
  document count, signup cap) MUST use it. Python's sqlite3 does not open a
  transaction for a bare SELECT, so a ``SELECT COUNT(*)`` followed by an
  ``INSERT`` inside one ``with conn:`` block executes in two different
  transactions and races.
"""
from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from . import config

# One number, one intent: how long a caller waits for the write lock.
BUSY_TIMEOUT_MS = 10_000

DDL = """
CREATE TABLE IF NOT EXISTS tenants(
  slug TEXT PRIMARY KEY,
  org TEXT NOT NULL,
  email TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  run_quota INTEGER NOT NULL DEFAULT 3,
  status TEXT NOT NULL DEFAULT 'active',
  consent_at TEXT
);
CREATE TABLE IF NOT EXISTS runs(
  id TEXT PRIMARY KEY,
  tenant TEXT NOT NULL REFERENCES tenants(slug),
  status TEXT NOT NULL CHECK(status IN ('queued','running','done','error')),
  drafter TEXT NOT NULL,
  question_count INTEGER,
  queued_at TEXT,
  started_at TEXT,
  finished_at TEXT,
  metrics_json TEXT,
  dir TEXT,
  error TEXT,
  error_detail TEXT,
  current_q INTEGER NOT NULL DEFAULT 0,
  total_q INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS uploads(
  id INTEGER PRIMARY KEY,
  tenant TEXT NOT NULL REFERENCES tenants(slug),
  source_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  bytes INTEGER NOT NULL,
  approved INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE(tenant, sha256),
  UNIQUE(tenant, source_id)
);
CREATE TABLE IF NOT EXISTS signup_events(
  ip TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signup_events_created ON signup_events(created_at);
CREATE TABLE IF NOT EXISTS approvals(
  id INTEGER PRIMARY KEY,
  run_id TEXT NOT NULL,
  question_id TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  note TEXT NOT NULL,
  ts TEXT NOT NULL
);
"""

# Columns added after the first release. SQLite has no "ADD COLUMN IF NOT
# EXISTS", so init() diffs against PRAGMA table_info and patches the gap.
MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("tenants", "consent_at", "TEXT"),
    ("runs", "error_detail", "TEXT"),
    ("runs", "current_q", "INTEGER NOT NULL DEFAULT 0"),
    ("runs", "total_q", "INTEGER NOT NULL DEFAULT 0"),
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def in_days(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def since_days(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def connect() -> sqlite3.Connection:
    config.DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    # busy_timeout first: journal_mode itself needs a brief lock, and under a
    # stampede we want it to wait rather than raise "database is locked".
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextlib.contextmanager
def immediate() -> Iterator[sqlite3.Connection]:
    """Yield a connection already holding the write lock (BEGIN IMMEDIATE).

    Autocommit is switched off explicitly (``isolation_level = None``) so that
    sqlite3 does not start a competing implicit transaction; the block commits
    on clean exit and rolls back on any exception. Do not nest, and do not use
    ``with conn:`` inside — the transaction is managed here.
    """
    conn = connect()
    conn.isolation_level = None
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        with contextlib.suppress(Exception):
            conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
    finally:
        with contextlib.suppress(Exception):
            conn.close()


def init() -> None:
    with connect() as conn:
        conn.executescript(DDL)
        for table, column, decl in MIGRATIONS:
            have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
