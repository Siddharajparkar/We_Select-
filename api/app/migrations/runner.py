"""Idempotent SQL migration runner (R23).

* Applies ``NNNN_name.sql`` files from ``migrations/sql`` in order, each in its own transaction.
* Serialised across replicas with ``sp_getapplock`` (session scope, 60 s wait).
* Records ``schema_migrations(version, name, applied_at)``.
* Runs before the API starts listening (see ``app.main``) and via ``python -m app.migrations.runner``.

T-SQL only: it is exercised against a real SQL Server in CI (tier T2). Unit tests cover the
file discovery, ordering, schema substitution and the orchestration with a fake connection.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.logging import logger

MIGRATIONS_DIR = Path(__file__).parent / "sql"
_FILE_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
LOCK_WAIT_MS = 60_000


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path

    def sql(self, schema: str) -> str:
        return self.path.read_text(encoding="utf-8").replace("[assess]", f"[{schema}]")


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    found: list[Migration] = []
    for p in sorted(directory.glob("*.sql")):
        match = _FILE_RE.match(p.name)
        if not match:
            raise MigrationError(f"migration file name must look like 0001_name.sql: {p.name}")
        found.append(Migration(int(match.group(1)), match.group(2), p))
    versions = [m.version for m in found]
    if len(versions) != len(set(versions)):
        raise MigrationError("duplicate migration version numbers")
    if versions != sorted(versions):
        raise MigrationError("migrations are not ordered")
    return found


def _scalar(conn: Any, sql: str, params: dict[str, Any] | None = None) -> Any:
    from sqlalchemy import text

    return conn.execute(text(sql), params or {}).scalar()


def run_migrations(engine: Any, schema: str = "assess", directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations; returns the names applied in this run."""
    from sqlalchemy import text

    migrations = discover(directory)
    applied_now: list[str] = []
    lock_resource = f"{schema}-migrations"

    # One AUTOCOMMIT connection holds the session-scoped app lock for the whole run.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if _scalar(conn, "SELECT COUNT(*) FROM sys.schemas WHERE name = :s", {"s": schema}) == 0:
            raise MigrationError(
                f"schema [{schema}] does not exist; create it with scripts/db/create-app-user.sql (OC-1B)"
            )
        rc = _scalar(
            conn,
            "DECLARE @r INT; EXEC @r = sp_getapplock @Resource = :res, @LockMode = 'Exclusive', "
            "@LockOwner = 'Session', @LockTimeout = :wait; SELECT @r",
            {"res": lock_resource, "wait": LOCK_WAIT_MS},
        )
        if rc is None or int(rc) < 0:
            raise MigrationError(f"could not obtain migration lock (code {rc})")
        try:
            conn.execute(
                text(
                    f"IF OBJECT_ID(N'[{schema}].[schema_migrations]', N'U') IS NULL "
                    f"CREATE TABLE [{schema}].[schema_migrations] ("
                    "version INT NOT NULL PRIMARY KEY, name NVARCHAR(200) NOT NULL, "
                    "applied_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME())"
                )
            )
            done = {
                int(r[0])
                for r in conn.execute(text(f"SELECT version FROM [{schema}].[schema_migrations]"))  # noqa: S608
            }
            for mig in migrations:
                if mig.version in done:
                    continue
                logger.info("applying migration", version=mig.version, name=mig.name)
                conn.exec_driver_sql("BEGIN TRANSACTION")
                try:
                    conn.exec_driver_sql("SET XACT_ABORT ON")
                    conn.exec_driver_sql(mig.sql(schema))
                    conn.execute(
                        text(f"INSERT INTO [{schema}].[schema_migrations] (version, name) VALUES (:v, :n)"),  # noqa: S608
                        {"v": mig.version, "n": mig.name},
                    )
                    conn.exec_driver_sql("COMMIT TRANSACTION")
                except Exception:
                    conn.exec_driver_sql("IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION")
                    raise
                applied_now.append(mig.name)
            logger.info("migrations applied", applied=applied_now, total=len(migrations))
        finally:
            conn.execute(
                text("EXEC sp_releaseapplock @Resource = :res, @LockOwner = 'Session'"), {"res": lock_resource}
            )
    return applied_now


def main(argv: list[str] | None = None) -> int:
    from ..config import ConfigError, load_settings
    from ..db.engine import create_sql_database

    try:
        settings = load_settings()
        if not settings.DATABASE_URL:
            raise ConfigError("DATABASE_URL is required to run migrations")
        db = create_sql_database(settings.DATABASE_URL)
        applied = run_migrations(db.engine, settings.DB_SCHEMA)
    except Exception as exc:
        logger.error("migration failed", error_type=type(exc).__name__, error=str(exc)[:300])
        return 1
    print(f"migrations applied: {', '.join(applied) if applied else '(none pending)'}")
    return 0


def iter_sql_files() -> Iterator[Path]:
    yield from sorted(MIGRATIONS_DIR.glob("*.sql"))


if __name__ == "__main__":
    sys.exit(main())
