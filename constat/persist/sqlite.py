"""SQLite repository: stdlib, WAL, one connection per repository, a lock
around writes. Local development and CI."""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import fields
from typing import Any

from .models import PRIMARY_KEY, TABLES
from .repo import Repository

_SQL_TYPES = {int: "INTEGER", float: "REAL", bool: "INTEGER"}


def _coltype(f) -> str:
    t = f.type
    if isinstance(t, str):
        for py, sql in _SQL_TYPES.items():
            if t == py.__name__ or t.startswith(f"Optional[{py.__name__}]"):
                return sql
        return "TEXT"
    return _SQL_TYPES.get(t, "TEXT")


def ddl() -> list[str]:
    out = []
    for name, cls in TABLES.items():
        cols = []
        for f in fields(cls):
            pk = " PRIMARY KEY" if f.name == PRIMARY_KEY[name] else ""
            cols.append(f"{f.name} {_coltype(f)}{pk}")
        out.append(f"CREATE TABLE IF NOT EXISTS {name} ({', '.join(cols)})")
    out += [
        "CREATE INDEX IF NOT EXISTS ix_items_qnr ON question_items(questionnaire_id)",
        "CREATE INDEX IF NOT EXISTS ix_items_tenant_state ON question_items(tenant, state)",
        "CREATE INDEX IF NOT EXISTS ix_actions_item ON review_actions(item_id)",
        "CREATE INDEX IF NOT EXISTS ix_metrics_tenant_kind ON metric_events(tenant, kind, at)",
        "CREATE INDEX IF NOT EXISTS ix_principals_tenant ON principals(tenant, email)",
    ]
    return out


class SqliteRepository(Repository):
    def __init__(self, path: str = ":memory:"):
        self.path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._lock:
            for stmt in ddl():
                self._conn.execute(stmt)

    def insert(self, table: str, obj) -> None:
        cls = self._check(table)
        if not isinstance(obj, cls):
            raise TypeError(f"{table} rows are {cls.__name__}, got {type(obj).__name__}")
        row = obj.to_row()
        cols = ", ".join(row)
        qs = ", ".join("?" for _ in row)
        with self._lock:
            self._conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", list(row.values()))

    def get(self, table: str, key: str):
        cls = self._check(table)
        cur = self._conn.execute(f"SELECT * FROM {table} WHERE {self._pk(table)} = ?", (key,))
        r = cur.fetchone()
        return cls.from_row(dict(r)) if r else None

    def list(self, table: str, where: dict[str, Any] | None = None, order: str = "",
             limit: int = 500, offset: int = 0) -> list:
        cls = self._check(table)
        sql, params = f"SELECT * FROM {table}", []
        if where:
            clauses = []
            for k, v in where.items():
                if isinstance(v, (list, tuple, set)):
                    clauses.append(f"{k} IN ({', '.join('?' for _ in v)})")
                    params.extend(v)
                elif v is None:
                    clauses.append(f"{k} IS NULL")
                else:
                    clauses.append(f"{k} = ?")
                    params.append(v.value if hasattr(v, "value") else v)
            sql += " WHERE " + " AND ".join(clauses)
        if order:
            col, _, direction = order.partition(" ")
            if not col.replace("_", "").isalnum():
                raise ValueError("bad order column")
            sql += f" ORDER BY {col} {'DESC' if direction.lower() == 'desc' else 'ASC'}"
        sql += " LIMIT ? OFFSET ?"
        params += [limit, offset]
        return [cls.from_row(dict(r)) for r in self._conn.execute(sql, params)]

    def update(self, table: str, key: str, fields_: dict[str, Any]) -> None:
        self._check(table)
        if not fields_:
            return
        from .models import _JSON_FIELDS
        import json
        vals = []
        for k, v in fields_.items():
            if hasattr(v, "value"):
                v = v.value
            elif k in _JSON_FIELDS or isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)
            elif isinstance(v, bool):
                v = 1 if v else 0
            vals.append(v)
        sets = ", ".join(f"{k} = ?" for k in fields_)
        with self._lock:
            cur = self._conn.execute(f"UPDATE {table} SET {sets} WHERE {self._pk(table)} = ?",
                                     vals + [key])
            if cur.rowcount == 0:
                raise KeyError(f"{table}:{key} not found")

    def count(self, table: str, where: dict[str, Any] | None = None) -> int:
        self._check(table)
        sql, params = f"SELECT COUNT(*) FROM {table}", []
        if where:
            sql += " WHERE " + " AND ".join(f"{k} = ?" for k in where)
            params = [v.value if hasattr(v, "value") else v for v in where.values()]
        return int(self._conn.execute(sql, params).fetchone()[0])

    def close(self) -> None:
        self._conn.close()
