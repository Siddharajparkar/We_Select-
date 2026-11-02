"""Phase 2: connection-string parsing, URL building, transient-error retry."""

from __future__ import annotations

import urllib.parse

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError

from app.db import engine as eng

ADO = "Server=tcp:myserver.database.windows.net,1433;Database=assessdb;User ID=app_user;Password=P@ss;w0rd;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30"


def test_parse_ado_connection_string() -> None:
    p = eng.parse_ado_connection_string(ADO)
    assert p["server"] == "tcp:myserver.database.windows.net,1433"
    assert p["database"] == "assessdb" and p["userid"] == "app_user" and p["connectiontimeout"] == "30"


def test_build_url_wraps_odbc_connect_string() -> None:
    url = eng.build_sqlalchemy_url(ADO.replace("P@ss;w0rd", "Pass1234"))
    assert url.startswith("mssql+pyodbc:///?odbc_connect=")
    odbc = urllib.parse.unquote_plus(url.split("odbc_connect=", 1)[1])
    assert "DRIVER={ODBC Driver 18 for SQL Server}" in odbc
    assert "SERVER=myserver.database.windows.net,1433" in odbc
    assert "DATABASE=assessdb" in odbc and "UID=app_user" in odbc and "PWD=Pass1234" in odbc
    assert "Encrypt=yes" in odbc and "TrustServerCertificate=no" in odbc


def test_build_url_honours_local_dev_options() -> None:
    odbc = urllib.parse.unquote_plus(
        eng.build_sqlalchemy_url(
            "Server=localhost,1433;Database=d;User ID=sa;Password=Dev1234;Encrypt=false;TrustServerCertificate=true"
        ).split("=", 1)[1]
    )
    assert "Encrypt=no" in odbc and "TrustServerCertificate=yes" in odbc and "SERVER=localhost,1433" in odbc


def test_default_port_is_1433() -> None:
    odbc = urllib.parse.unquote_plus(
        eng.build_sqlalchemy_url("Server=host;Database=d;User ID=u;Password=p").split("=", 1)[1]
    )
    assert "SERVER=host,1433" in odbc


def test_existing_sqlalchemy_urls_pass_through() -> None:
    assert eng.build_sqlalchemy_url("mssql+pyodbc://u:p@h/d?driver=x") == "mssql+pyodbc://u:p@h/d?driver=x"


def test_incomplete_connection_string_error_does_not_echo_secrets() -> None:
    with pytest.raises(eng.ConnectionStringError) as exc:
        eng.build_sqlalchemy_url("Server=h;Password=TopSecret99")
    assert "TopSecret99" not in str(exc.value)


def _dbapi_error(msg: str, invalidated: bool = False) -> DBAPIError:
    return OperationalError("stmt", {}, Exception(msg), connection_invalidated=invalidated)


@pytest.mark.parametrize("number", sorted(eng.TRANSIENT_ERROR_NUMBERS))
def test_transient_numbers_are_detected(number: int) -> None:
    assert eng.is_transient(_dbapi_error(f"('HY000', '[HY000] Error {number}: try again')"))


def test_non_transient_errors_are_not_retried() -> None:
    assert not eng.is_transient(_dbapi_error("Violation of UNIQUE KEY constraint 2627"))
    assert not eng.is_transient(ValueError("40613"))
    assert eng.is_transient(_dbapi_error("connection dropped", invalidated=True))


def test_with_retry_backs_off_exponentially_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(eng.time, "sleep", sleeps.append)
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _dbapi_error("Error 40613 database not available")
        return "ok"

    assert eng.with_retry(flaky) == "ok"
    assert calls["n"] == 3 and sleeps == [0.2, 0.4]


def test_with_retry_gives_up_after_three_tries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eng.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def always() -> None:
        calls["n"] += 1
        raise _dbapi_error("Error 49918")

    with pytest.raises(OperationalError):
        eng.with_retry(always)
    assert calls["n"] == 3


def test_with_retry_does_not_retry_logic_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eng.time, "sleep", lambda s: pytest.fail("must not sleep"))
    with pytest.raises(KeyError):
        eng.with_retry(lambda: {}["x"])


def test_memory_database_enforces_foreign_keys_and_is_isolated() -> None:
    from sqlalchemy import text

    a, b = eng.create_memory_database(), eng.create_memory_database()
    with a.begin() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        conn.execute(text("CREATE TABLE only_in_a (id INT)"))
    with b.begin() as conn, pytest.raises(Exception, match="no such table"):
        conn.execute(text("SELECT * FROM only_in_a"))
