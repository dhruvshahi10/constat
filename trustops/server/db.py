"""SQLite persistence. One connection per call site, WAL mode, single process."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from . import config

DDL = """
CREATE TABLE IF NOT EXISTS tenants(
  slug TEXT PRIMARY KEY,
  org TEXT NOT NULL,
  email TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  run_quota INTEGER NOT NULL DEFAULT 3,
  status TEXT NOT NULL DEFAULT 'active'
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
  error TEXT
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


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def in_days(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def connect() -> sqlite3.Connection:
    config.DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init() -> None:
    with connect() as conn:
        conn.executescript(DDL)
