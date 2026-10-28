"""Repository interface and factory.

The interface is deliberately generic: insert, get, list, update, count over
named tables of dataclass rows. Domain rules (state transitions, the
second-person rule, spot checks) live in constat.workflow, not in storage.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable, Optional

from .models import PRIMARY_KEY, TABLES


class Repository(ABC):
    @abstractmethod
    def insert(self, table: str, obj) -> None: ...

    @abstractmethod
    def get(self, table: str, key: str):
        ...

    @abstractmethod
    def list(self, table: str, where: dict[str, Any] | None = None, order: str = "",
             limit: int = 500, offset: int = 0) -> list: ...

    @abstractmethod
    def update(self, table: str, key: str, fields: dict[str, Any]) -> None: ...

    @abstractmethod
    def count(self, table: str, where: dict[str, Any] | None = None) -> int: ...

    @abstractmethod
    def close(self) -> None: ...

    # ---- helpers shared by implementations ---------------------------------
    @staticmethod
    def _check(table: str) -> type:
        if table not in TABLES:
            raise KeyError(f"unknown table {table!r}")
        return TABLES[table]

    @staticmethod
    def _pk(table: str) -> str:
        return PRIMARY_KEY[table]

    def upsert(self, table: str, obj) -> None:
        key = getattr(obj, self._pk(table))
        if self.get(table, key) is None:
            self.insert(table, obj)
        else:
            row = obj.to_row()
            row.pop(self._pk(table))
            self.update(table, key, row)


def make_repo(url: str) -> Repository:
    """sqlite:///path/to/file.db | sqlite:///:memory: | postgresql://..."""
    if url.startswith("sqlite://"):
        from .sqlite import SqliteRepository
        path = url[len("sqlite://"):]
        if path.startswith("/") and not path.startswith("//"):
            path = path  # sqlite:///abs/path -> /abs/path
        return SqliteRepository(path.lstrip("/") if path.startswith("/:memory:") else path)
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        from .postgres import PostgresRepository
        return PostgresRepository(url)
    raise ValueError(f"unsupported DATABASE_URL scheme in {url!r}")
