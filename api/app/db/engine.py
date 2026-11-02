"""Database engine construction (SQL Server via pyodbc, or in-memory SQLite) and helpers."""

from __future__ import annotations

import re
import threading
import time
import urllib.parse
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.pool import StaticPool

from ..core.logging import logger

T = TypeVar("T")

# Azure SQL transient error numbers (Prompt A 2.1)
TRANSIENT_ERROR_NUMBERS = frozenset({4060, 40197, 40501, 40613, 49918, 49919, 49920, 10928, 10929, 10053, 10054, 10060})
RETRIES = 3
BASE_DELAY_S = 0.2


class ConnectionStringError(ValueError):
    """Raised for an unparseable DATABASE_URL (message never contains the value)."""


def parse_ado_connection_string(raw: str) -> dict[str, str]:
    """Parse an ADO.NET-style string: ``Server=tcp:host,1433;Database=x;User ID=u;Password=p;...``."""
    parts: dict[str, str] = {}
    for chunk in raw.split(";"):
        if not chunk.strip() or "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        parts[key.strip().lower().replace(" ", "")] = value.strip()
    return parts


def build_sqlalchemy_url(database_url: str, driver: str = "ODBC Driver 18 for SQL Server") -> str:
    """Turn ``DATABASE_URL`` (ADO.NET style, or an existing ``mssql+pyodbc://`` URL) into a SQLAlchemy URL."""
    if database_url.startswith(("mssql+pyodbc://", "mssql://")):
        return database_url
    p = parse_ado_connection_string(database_url)
    server = p.get("server") or p.get("datasource")
    database = p.get("database") or p.get("initialcatalog")
    user = p.get("userid") or p.get("uid") or p.get("user")
    password = p.get("password") or p.get("pwd")
    if not (server and database and user and password):
        raise ConnectionStringError("DATABASE_URL must include Server, Database, User ID and Password")
    server = re.sub(r"^tcp:", "", server, flags=re.IGNORECASE).replace(",", ":", 1)
    host, _, port = server.partition(":")
    encrypt = "no" if p.get("encrypt", "yes").lower() in ("false", "no") else "yes"
    trust = "yes" if p.get("trustservercertificate", "no").lower() in ("true", "yes") else "no"
    timeout = p.get("connectiontimeout", "30")
    odbc = (
        f"DRIVER={{{driver}}};SERVER={host},{port or 1433};DATABASE={database};UID={user};PWD={password};"
        f"Encrypt={encrypt};TrustServerCertificate={trust};Connection Timeout={timeout}"
    )
    return "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(odbc)


def is_transient(exc: BaseException) -> bool:
    if not isinstance(exc, DBAPIError):
        return False
    if isinstance(exc, OperationalError) and exc.connection_invalidated:
        return True
    text = str(getattr(exc, "orig", exc))
    return any(re.search(rf"\b{n}\b", text) for n in TRANSIENT_ERROR_NUMBERS)


def with_retry(fn: Callable[[], T], *, retries: int = RETRIES, base_delay: float = BASE_DELAY_S) -> T:
    """Run ``fn``; retry transient failures with exponential backoff (200 ms, 400 ms, ...)."""
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            attempt += 1
            if attempt >= retries or not is_transient(exc):
                raise
            delay = base_delay * (2 ** (attempt - 1))
            logger.warn("transient database error; retrying", attempt=attempt, delay_s=delay)
            time.sleep(delay)


class Database:
    """Wraps an Engine; serialises SQLite access (single shared in-memory connection)."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.dialect = engine.dialect.name
        self._lock = threading.RLock()

    @contextmanager
    def begin(self) -> Iterator[Connection]:
        if self.dialect == "sqlite":
            with self._lock, self.engine.begin() as conn:
                yield conn
        else:
            with self.engine.begin() as conn:
                yield conn

    def dispose(self) -> None:
        if self.dialect == "sqlite":
            with self._lock:  # never close the shared connection under a running statement
                self.engine.dispose()
        else:
            self.engine.dispose()


def create_memory_database() -> Database:
    """Fresh, isolated in-memory SQLite with enforced foreign keys and real transactions."""
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn: Any, _record: Any) -> None:
        dbapi_conn.isolation_level = None  # we emit BEGIN ourselves (SQLAlchemy recipe)
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn: Connection) -> None:
        conn.exec_driver_sql("BEGIN")

    return Database(engine)


def create_sql_database(database_url: str) -> Database:
    engine = create_engine(
        build_sqlalchemy_url(database_url),
        pool_size=10,
        max_overflow=0,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={"timeout": 15},  # query/login timeout seconds (pyodbc)
        fast_executemany=True,
    )
    return Database(engine)
