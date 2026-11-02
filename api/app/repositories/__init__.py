"""Repository container.

One implementation (SQLAlchemy Core) serves both backends:
* ``REPO_BACKEND=memory`` -> in-memory SQLite with the same FKs, uniques, checks and filtered index.
* ``REPO_BACKEND=sql``    -> SQL Server / Azure SQL via pyodbc.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy import Table

from ..core.clock import Clock, SystemClock
from ..db.engine import Database, create_memory_database, create_sql_database
from ..db.schema import build_metadata
from .base import Ctx, Exec
from .system import SystemRepo
from .tenant_scoped import (
    AssessmentsRepo,
    AttemptsRepo,
    AuditRepo,
    JobsRepo,
    LoginAttemptsRepo,
    ParticipantsRepo,
    QuestionsRepo,
    ResponsesRepo,
    ScoresRepo,
    SessionsRepo,
    TenantsRepo,
    UsersRepo,
)

T = TypeVar("T")

__all__ = ["Repositories", "create_repositories"]


class Repositories:
    def __init__(self, db: Database, tables: dict[str, Table], clock: Clock, conn: object | None = None) -> None:
        self.db = db
        self.tables = tables
        self.clock = clock
        c = Ctx(Exec(db, conn), tables, clock)  # type: ignore[arg-type]
        self.tenants = TenantsRepo(c)
        self.users = UsersRepo(c)
        self.sessions = SessionsRepo(c)
        self.login_attempts = LoginAttemptsRepo(c)
        self.assessments = AssessmentsRepo(c)
        self.questions = QuestionsRepo(c)
        self.participants = ParticipantsRepo(c)
        self.attempts = AttemptsRepo(c)
        self.responses = ResponsesRepo(c)
        self.scores = ScoresRepo(c)
        self.jobs = JobsRepo(c)
        self.audit = AuditRepo(c)
        self.system = SystemRepo(c)

    def with_transaction(self, fn: Callable[[Repositories], T]) -> T:
        """Run ``fn`` in one transaction; any exception rolls everything back."""
        with self.db.begin() as conn:
            return fn(Repositories(self.db, self.tables, self.clock, conn))

    def ping(self) -> None:
        """Cheap connectivity check."""
        from sqlalchemy import text

        with self.db.begin() as conn:
            conn.execute(text("SELECT 1"))


def create_repositories(
    backend: str, *, database_url: str = "", schema: str = "assess", clock: Clock | None = None
) -> Repositories:
    clock = clock or SystemClock()
    if backend == "memory":
        db = create_memory_database()
        md = build_metadata(None)
        md.create_all(db.engine)
    elif backend == "sql":
        db = create_sql_database(database_url)
        md = build_metadata(schema)  # tables are created by the T-SQL migrations, never by create_all
    else:
        raise ValueError(f"unknown REPO_BACKEND {backend!r}")
    return Repositories(
        db, dict(md.tables) if backend == "memory" else {k.split(".")[-1]: v for k, v in md.tables.items()}, clock
    )
