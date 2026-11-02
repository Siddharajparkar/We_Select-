"""Shared plumbing for repositories: execution context, row mapping, constraint classification."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy import Connection, Table
from sqlalchemy.exc import IntegrityError

from ..core.clock import Clock
from ..db.engine import Database, with_retry
from .models import RepositoryError

T = TypeVar("T")


class Exec:
    """Runs units of work either on a fixed connection (inside a transaction) or on a fresh
    one (auto-commit per call, with transient-error retry)."""

    def __init__(self, db: Database, conn: Connection | None = None) -> None:
        self.db = db
        self.conn = conn

    def run(self, fn: Callable[[Connection], T]) -> T:
        if self.conn is not None:
            return fn(self.conn)

        def attempt() -> T:
            with self.db.begin() as conn:
                return fn(conn)

        return with_retry(attempt)


class Ctx:
    """Everything a repository needs."""

    def __init__(self, x: Exec, tables: dict[str, Table], clock: Clock) -> None:
        self.x = x
        self.t = tables
        self.clock = clock


def constraint_kind(exc: IntegrityError) -> str:
    """'fk' | 'unique' | 'check' for both SQLite and SQL Server messages."""
    msg = str(getattr(exc, "orig", exc)).upper()
    if "FOREIGN KEY" in msg:
        return "fk"
    if "UNIQUE" in msg or "DUPLICATE" in msg:
        return "unique"
    return "check"


def fk_error() -> RepositoryError:
    return RepositoryError("FK_VIOLATION", "Foreign key constraint failed")


def err_text(exc: IntegrityError) -> str:
    return str(getattr(exc, "orig", exc)).lower()


def num(value: Any) -> float | None:
    return None if value is None else float(value)
