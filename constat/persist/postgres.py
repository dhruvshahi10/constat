"""Postgres repository (Supabase). Same statements as SQLite with %s
placeholders; psycopg imported lazily so the engine has no hard dependency."""
from __future__ import annotations

import json
from dataclasses import fields
from typing import Any

from .models import PRIMARY_KEY, TABLES, _JSON_FIELDS
from .repo import Repository

_PG_TYPES = {"int": "BIGINT", "float": "DOUBLE PRECISION", "bool": "BOOLEAN"}


def _coltype(f) -> str:
    t = f.type if isinstance(f.type, str) else f.type.__name__
    for py, sql in _PG_TYPES.items():
        if t == py or t.startswith(f"Optional[{py}]"):
            return sql
    return "TEXT"


def ddl() -> list[str]:
    out = []
    for name, cls in TABLES.items():
        cols = [f"{f.name} {_coltype(f)}{' PRIMARY KEY' if f.name == PRIMARY_KEY[name] else ''}"
                for f in fields(cls)]
        out.append(f"CREATE TABLE IF NOT EXISTS {name} ({', '.join(cols)})")
    out += [
        "CREATE INDEX IF NOT EXISTS ix_items_qnr ON question_items(questionnaire_id)",
        "CREATE INDEX IF NOT EXISTS ix_items_tenant_state ON question_items(tenant, state)",
        "CREATE INDEX IF NOT EXISTS ix_actions_item ON review_actions(item_id)",
        "CREATE INDEX IF NOT EXISTS ix_metrics_tenant_kind ON metric_events(tenant, kind, at)",
    ]
    return out


class PostgresRepository(Repository):
    def __init__(self, url: str):
        try:
            import psycopg  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("psycopg is not installed; `pip install psycopg[binary]`") from e
        self._conn = psycopg.connect(url, autocommit=True)
        with self._conn.cursor() as cur:
            for stmt in ddl():
                cur.execute(stmt)

    @staticmethod
    def _coerce(k, v):
        if hasattr(v, "value"):
            return v.value
        if k in _JSON_FIELDS or isinstance(v, (list, dict)):
            return json.dumps(v, ensure_ascii=False)
        return v

    def insert(self, table: str, obj) -> None:
        self._check(table)
        row = obj.to_row()
        # to_row() encodes bools as 0/1 for SQLite; Postgres wants real booleans
        for f in fields(type(obj)):
            if (f.type in ("bool", bool)) and f.name in row:
                row[f.name] = bool(row[f.name])
        cols = ", ".join(row)
        qs = ", ".join("%s" for _ in row)
        with self._conn.cursor() as cur:
            cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", list(row.values()))

    def get(self, table: str, key: str):
        cls = self._check(table)
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {table} WHERE {self._pk(table)} = %s", (key,))
            r = cur.fetchone()
            if not r:
                return None
            names = [d.name for d in cur.description]
        return cls.from_row(dict(zip(names, r)))

    def list(self, table: str, where: dict[str, Any] | None = None, order: str = "",
             limit: int = 500, offset: int = 0) -> list:
        cls = self._check(table)
        sql, params = f"SELECT * FROM {table}", []
        if where:
            clauses = []
            for k, v in where.items():
                if isinstance(v, (list, tuple, set)):
                    clauses.append(f"{k} = ANY(%s)")
                    params.append(list(v))
                elif v is None:
                    clauses.append(f"{k} IS NULL")
                else:
                    clauses.append(f"{k} = %s")
                    params.append(self._coerce(k, v))
            sql += " WHERE " + " AND ".join(clauses)
        if order:
            col, _, direction = order.partition(" ")
            if not col.replace("_", "").isalnum():
                raise ValueError("bad order column")
            sql += f" ORDER BY {col} {'DESC' if direction.lower() == 'desc' else 'ASC'}"
        sql += " LIMIT %s OFFSET %s"
        params += [limit, offset]
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            names = [d.name for d in cur.description]
            return [cls.from_row(dict(zip(names, r))) for r in cur.fetchall()]

    def update(self, table: str, key: str, fields_: dict[str, Any]) -> None:
        self._check(table)
        if not fields_:
            return
        sets = ", ".join(f"{k} = %s" for k in fields_)
        vals = [self._coerce(k, v) for k, v in fields_.items()]
        with self._conn.cursor() as cur:
            cur.execute(f"UPDATE {table} SET {sets} WHERE {self._pk(table)} = %s", vals + [key])
            if cur.rowcount == 0:
                raise KeyError(f"{table}:{key} not found")

    def count(self, table: str, where: dict[str, Any] | None = None) -> int:
        self._check(table)
        sql, params = f"SELECT COUNT(*) FROM {table}", []
        if where:
            sql += " WHERE " + " AND ".join(f"{k} = %s" for k in where)
            params = [self._coerce(k, v) for k, v in where.items()]
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return int(cur.fetchone()[0])

    def close(self) -> None:
        self._conn.close()
