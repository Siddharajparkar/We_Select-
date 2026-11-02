#!/usr/bin/env python3
"""CI helper (tier T2): prepare a throw-away database on the SQL Server service container.

* enables contained-database authentication (needed for the contained app user),
* creates the database, then the `assess` schema and the least-privilege `assess_app` user
  by running scripts/db/create-app-user.sql (the same script the office runs, OC-1B),
* exports TEST_DATABASE_URL for later steps via $GITHUB_ENV (password is masked first).

Environment: SA_PASSWORD (required), CI_APP_PASSWORD (required), SQL_HOST=localhost, SQL_PORT=1433, CI_DB=assess_ci.
The passwords exist only inside the ephemeral runner. Never prints them.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pyodbc

REPO = Path(__file__).resolve().parents[2]
DRIVER = "ODBC Driver 18 for SQL Server"


def connect(host: str, port: str, database: str, user: str, password: str) -> pyodbc.Connection:
    cs = (
        f"DRIVER={{{DRIVER}}};SERVER={host},{port};DATABASE={database};UID={user};PWD={password};"
        "Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=15"
    )
    return pyodbc.connect(cs, autocommit=True)


def wait_for_server(host: str, port: str, sa_password: str, timeout: int = 120) -> pyodbc.Connection:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            return connect(host, port, "master", "sa", sa_password)
        except pyodbc.Error as exc:
            last = exc
            time.sleep(3)
    raise SystemExit(f"SQL Server not ready after {timeout}s: {type(last).__name__}")


def main() -> int:
    sa_password = os.environ.get("SA_PASSWORD", "")
    app_password = os.environ.get("CI_APP_PASSWORD", "")
    if not sa_password or not app_password:
        print("SA_PASSWORD and CI_APP_PASSWORD are required", file=sys.stderr)
        return 2
    host, port, db = (
        os.environ.get("SQL_HOST", "localhost"),
        os.environ.get("SQL_PORT", "1433"),
        os.environ.get("CI_DB", "assess_ci"),
    )
    if not db.replace("_", "").isalnum():
        print("CI_DB must be a simple identifier", file=sys.stderr)
        return 2

    master = wait_for_server(host, port, sa_password)
    cur = master.cursor()
    cur.execute("EXEC sp_configure 'contained database authentication', 1; RECONFIGURE;")
    cur.execute(f"IF DB_ID(N'{db}') IS NULL CREATE DATABASE [{db}];")
    cur.execute(f"ALTER DATABASE [{db}] SET CONTAINMENT = PARTIAL;")
    master.close()

    sql = (REPO / "scripts" / "db" / "create-app-user.sql").read_text().replace("<APP_USER_PASSWORD>", app_password)
    dbconn = connect(host, port, db, "sa", sa_password)
    dbconn.cursor().execute(sql)
    dbconn.close()

    # prove the app user can log in and sees only its schema
    app = connect(host, port, db, "assess_app", app_password)
    row = app.cursor().execute("SELECT SCHEMA_NAME(schema_id) FROM sys.schemas WHERE name = 'assess'").fetchone()
    app.close()
    if row is None:
        print("assess schema not visible to assess_app", file=sys.stderr)
        return 1

    url = f"Server=tcp:{host},{port};Database={db};User ID=assess_app;Password={app_password};Encrypt=yes;TrustServerCertificate=yes"
    gh_env = os.environ.get("GITHUB_ENV")
    if gh_env:
        print(f"::add-mask::{app_password}")
        with open(gh_env, "a", encoding="utf-8") as fh:
            fh.write(f"TEST_DATABASE_URL={url}\n")
    print(f"database [{db}] ready; schema [assess] owned by assess_app; TEST_DATABASE_URL exported")
    return 0


if __name__ == "__main__":
    sys.exit(main())
