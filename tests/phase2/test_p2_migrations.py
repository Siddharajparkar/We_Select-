"""Phase 2: migration runner - file rules and orchestration (fake connection), plus real SQL Server tests (marked sql)."""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

import pytest

from app.migrations import runner
from app.migrations.runner import MIGRATIONS_DIR, MigrationError, discover, run_migrations

SQL_REQUIRED = pytest.mark.sql


# ── discovery rules ────────────────────────────────────────────────────────────────────────
def test_real_migrations_are_discovered_in_order() -> None:
    migs = discover()
    assert [m.version for m in migs][:1] == [1] and migs[0].name == "init"
    assert [m.version for m in migs] == sorted(m.version for m in migs)


def test_bad_file_names_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "init.sql").write_text("SELECT 1")
    with pytest.raises(MigrationError, match="0001_name.sql"):
        discover(tmp_path)


def test_duplicate_versions_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_text("x")
    (tmp_path / "0001_b.sql").write_text("x")
    with pytest.raises(MigrationError, match="duplicate"):
        discover(tmp_path)


def test_schema_name_is_substituted_in_sql(tmp_path: Path) -> None:
    (tmp_path / "0001_x.sql").write_text("CREATE TABLE [assess].[t] (id INT)")
    assert discover(tmp_path)[0].sql("tenant_a") == "CREATE TABLE [tenant_a].[t] (id INT)"


def test_every_create_in_init_is_guarded_so_reruns_are_noops() -> None:
    sql = (MIGRATIONS_DIR / "0001_init.sql").read_text()
    creates = len(re.findall(r"CREATE TABLE \[assess\]", sql))
    guards = len(re.findall(r"IF OBJECT_ID\(N'\[assess\]\.\[\w+\]', N'U'\) IS NULL", sql))
    assert creates == guards == 12
    assert "SYSUTCDATETIME()" in sql  # UTC timestamps
    assert "GO\n" not in sql, "runner executes each file as a single batch: no GO separators"


def test_alter_migrations_are_idempotent_and_batch_safe() -> None:
    for f in sorted(MIGRATIONS_DIR.glob("*.sql"))[1:]:
        sql = f.read_text()
        alters = re.findall(r"ALTER TABLE \[assess\]\.\[(\w+)\]\s+ADD\s+\[(\w+)\]", sql)
        guards = re.findall(r"IF COL_LENGTH\(N'\[assess\]\.\[(\w+)\]', N'(\w+)'\) IS NULL", sql)
        assert alters and sorted(alters) == sorted(guards), f.name  # every added column has its own guard
        assert "GO\n" not in sql and "dbo" not in sql.lower()


# ── orchestration with a fake connection ───────────────────────────────────────────────────
class FakeResult:
    def __init__(self, scalar: Any = None, rows: list[tuple[Any, ...]] | None = None) -> None:
        self._scalar, self._rows = scalar, rows or []

    def scalar(self) -> Any:
        return self._scalar

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._rows)


class FakeConn:
    def __init__(
        self, *, schema_exists: bool = True, lock_rc: int = 0, applied: tuple[int, ...] = (), fail_on: str | None = None
    ) -> None:
        self.log: list[str] = []
        self.schema_exists, self.lock_rc, self.applied, self.fail_on = schema_exists, lock_rc, applied, fail_on

    def __enter__(self) -> FakeConn:
        return self

    def __exit__(self, *_: object) -> None:
        self.log.append("CLOSE")

    def execution_options(self, **kw: Any) -> FakeConn:
        assert kw == {"isolation_level": "AUTOCOMMIT"}
        return self

    def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> FakeResult:
        text = str(stmt)
        self.log.append(text.split("\n")[0][:70])
        if "sys.schemas" in text:
            return FakeResult(1 if self.schema_exists else 0)
        if "sp_getapplock" in text:
            return FakeResult(self.lock_rc)
        if "SELECT version" in text:
            return FakeResult(rows=[(v,) for v in self.applied])
        return FakeResult()

    def exec_driver_sql(self, sql: str) -> None:
        head = sql.strip().split("\n")[0][:40]
        self.log.append(f"DRV:{head}")
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("boom in migration")


class FakeEngine:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    def connect(self) -> FakeConn:
        return self.conn


def test_fresh_database_applies_init_inside_a_transaction_under_the_app_lock() -> None:
    conn = FakeConn()
    applied = run_migrations(FakeEngine(conn), "assess")
    assert applied == [m.name for m in discover()]
    log = conn.log
    assert log.index(next(x for x in log if "sys.schemas" in x or "SELECT COUNT" in x)) < next(
        i for i, x in enumerate(log) if "sp_getapplock" in x or "DECLARE @r" in x
    )
    begin = log.index("DRV:BEGIN TRANSACTION")
    assert log[begin + 1].startswith("DRV:SET XACT_ABORT ON")
    assert "DRV:COMMIT TRANSACTION" in log[begin:]
    assert any("INSERT INTO [assess].[schema_migrations]" in x for x in log)
    assert any("sp_releaseapplock" in x for x in log) and log[-1] == "CLOSE"


def test_second_run_is_a_noop() -> None:
    conn = FakeConn(applied=tuple(m.version for m in discover()))
    assert run_migrations(FakeEngine(conn), "assess") == []
    assert "DRV:BEGIN TRANSACTION" not in conn.log
    assert any("sp_releaseapplock" in x for x in conn.log)


def test_failure_rolls_back_releases_lock_and_propagates() -> None:
    conn = FakeConn(fail_on="CREATE TABLE [assess].[tenants]")
    with pytest.raises(RuntimeError, match="boom"):
        run_migrations(FakeEngine(conn), "assess")
    assert any(x.startswith("DRV:IF @@TRANCOUNT > 0 ROLLBACK") for x in conn.log)
    assert "DRV:COMMIT TRANSACTION" not in conn.log
    assert any("sp_releaseapplock" in x for x in conn.log)


def test_missing_schema_gives_actionable_error_before_taking_the_lock() -> None:
    conn = FakeConn(schema_exists=False)
    with pytest.raises(MigrationError, match=r"create-app-user\.sql"):
        run_migrations(FakeEngine(conn), "assess")
    assert not any("sp_getapplock" in x or "DECLARE @r" in x for x in conn.log)


def test_lock_timeout_aborts() -> None:
    conn = FakeConn(lock_rc=-1)
    with pytest.raises(MigrationError, match="lock"):
        run_migrations(FakeEngine(conn), "assess")
    assert "DRV:BEGIN TRANSACTION" not in conn.log


def test_cli_returns_1_on_failure_without_leaking_connection_details(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("REPO_BACKEND", "sql")
    monkeypatch.setenv(
        "DATABASE_URL", "Server=tcp:nonexistent.invalid,1433;Database=d;User ID=u;Password=SuperSecret123;"
    )
    monkeypatch.setattr(
        runner,
        "run_migrations",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("login failed Password=SuperSecret123")),
    )
    assert runner.main([]) == 1
    cap = capsys.readouterr()
    assert "SuperSecret123" not in cap.out + cap.err


def test_cli_requires_database_url(capsys: pytest.CaptureFixture[str]) -> None:
    assert runner.main([]) == 1
    assert "DATABASE_URL" in capsys.readouterr().err


# ── real SQL Server (CI tier T2) ───────────────────────────────────────────────────────────
@SQL_REQUIRED
def test_sql_server_migrations_apply_twice_and_create_all_tables(_sql_repos_session) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    engine = _sql_repos_session.db.engine
    assert run_migrations(engine, "assess") == []  # fixture already applied; second run is a no-op
    with engine.connect() as conn:
        names = {r[0] for r in conn.execute(text("SELECT name FROM sys.tables WHERE schema_id = SCHEMA_ID('assess')"))}
        versions = [
            r[0] for r in conn.execute(text("SELECT version FROM [assess].[schema_migrations] ORDER BY version"))
        ]
    assert {"tenants", "users", "sessions", "login_attempts", "assessments", "questions", "participants",
            "attempts", "responses", "scores", "jobs", "audit_log", "schema_migrations"} <= names  # fmt: skip
    assert versions == [m.version for m in discover()]


@SQL_REQUIRED
def test_sql_server_parallel_runners_do_not_corrupt_state(_sql_repos_session) -> None:  # type: ignore[no-untyped-def]
    engine = _sql_repos_session.db.engine
    results: list[Any] = []

    def go() -> None:
        try:
            results.append(run_migrations(engine, "assess"))
        except Exception as exc:  # noqa: BLE001
            results.append(exc)

    threads = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert all(r == [] for r in results), results


@SQL_REQUIRED
def test_sql_server_enforces_isjson_and_filtered_index(_sql_repos_session) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    repos = _sql_repos_session
    t = repos.tenants.create(name="Json")
    u = repos.users.create(t.id, name="U", email="json@x.com", password_hash="h", role="admin")
    a = repos.assessments.create(t.id, title="x", sections=[], created_by=u.id)
    with pytest.raises(IntegrityError), repos.db.begin() as conn:
        conn.execute(text("UPDATE [assess].[assessments] SET sections_json = 'not json' WHERE id = :i"), {"i": a.id})
