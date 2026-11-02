"""Phase 0: core libraries - clock, ids, errors, logging."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

import pytest

from app.core import logging as applog
from app.core.clock import FakeClock, SystemClock
from app.core.errors import AppError
from app.core.ids import (
    generate_secure_token,
    hash_token,
    is_uuid,
    is_uuid4,
    new_id,
    timing_safe_equal,
)


# ── Clock ───────────────────────────────────────────────────────────────────────────────────
def test_system_clock_returns_aware_utc_now() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None and now.utcoffset() == timedelta(0)
    assert abs((datetime.now(UTC) - now).total_seconds()) < 5


def test_fake_clock_is_deterministic_and_advances() -> None:
    c = FakeClock(datetime(2026, 11, 1, 12, 0, tzinfo=UTC))
    assert c.now() == c.now() == datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    c.advance_seconds(30)
    c.advance_minutes(1)
    c.advance_hours(1)
    c.advance_days(1)
    assert c.now() == datetime(2026, 11, 2, 13, 1, 30, tzinfo=UTC)
    c.advance(seconds=-90)
    assert c.now() == datetime(2026, 11, 2, 13, 0, 0, tzinfo=UTC)


def test_fake_clock_set_time_and_naive_inputs_become_utc() -> None:
    c = FakeClock(datetime(2026, 1, 1))  # naive
    assert c.now().tzinfo is UTC or c.now().utcoffset() == timedelta(0)
    c.set_time(datetime(2026, 5, 5, 5, 5, tzinfo=UTC))
    assert c.now().month == 5


# ── Ids ─────────────────────────────────────────────────────────────────────────────────────
def test_new_id_is_uuid4_and_unique() -> None:
    ids = {new_id() for _ in range(200)}
    assert len(ids) == 200
    assert all(is_uuid4(i) for i in ids)


def test_is_uuid_rejects_garbage() -> None:
    assert is_uuid(new_id())
    for bad in ["", "not-a-uuid", None, 123, "1234", new_id() + "x"]:
        assert not is_uuid(bad)


def test_hash_token_is_sha256_hex_and_stable() -> None:
    h = hash_token("abc")
    assert h == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert re.fullmatch(r"[0-9a-f]{64}", hash_token("anything"))
    assert hash_token("x") != hash_token("y")


def test_secure_token_is_urlsafe_and_high_entropy() -> None:
    tokens = {generate_secure_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{43}", t) for t in tokens)  # 32 bytes, no padding


def test_timing_safe_equal() -> None:
    assert timing_safe_equal("secret", "secret")
    assert not timing_safe_equal("secret", "Secret")
    assert not timing_safe_equal("a", "ab")


# ── Errors ──────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("factory", "status", "code"),
    [
        (lambda: AppError.bad_request("x"), 400, "VALIDATION_ERROR"),
        (lambda: AppError.unauthenticated(), 401, "UNAUTHENTICATED"),
        (lambda: AppError.forbidden(), 403, "FORBIDDEN"),
        (lambda: AppError.not_found(), 404, "NOT_FOUND"),
        (lambda: AppError.conflict("EMAIL_EXISTS", "x"), 409, "EMAIL_EXISTS"),
        (lambda: AppError.gone("EXPIRED", "x"), 410, "EXPIRED"),
        (lambda: AppError.unprocessable("BAD", "x"), 422, "BAD"),
        (lambda: AppError.too_many_requests("SLOW", "x", 5), 429, "SLOW"),
        (lambda: AppError.internal(), 500, "INTERNAL"),
        (lambda: AppError.service_unavailable("DOWN", "x"), 503, "DOWN"),
    ],
)
def test_error_factories(factory, status: int, code: str) -> None:  # type: ignore[no-untyped-def]
    err = factory()
    assert (err.status, err.code) == (status, code)
    body = err.to_dict()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code


def test_error_envelope_includes_details_only_when_present() -> None:
    assert "details" not in AppError.not_found("nope").to_dict()["error"]
    d = AppError.bad_request("bad", [{"path": "email", "message": "required"}]).to_dict()
    assert d["error"]["details"] == [{"path": "email", "message": "required"}]
    assert AppError.too_many_requests("SLOW", "x", 7).retry_after == 7


# ── Logging / redaction ────────────────────────────────────────────────────────────────────
def test_redact_replaces_secret_keys_recursively() -> None:
    data = {
        "password": "p", "Authorization": "Bearer abc", "x-platform-key": "k", "ok": "fine",
        "nested": {"token": "t", "FOUNDRY_KEY": "f", "list": [{"cookie": "c", "keep": 1}]},
        "database_url": "Server=x;Password=y", "ACS_CONNECTION_STRING": "endpoint=...;accesskey=z",
    }  # fmt: skip
    out = applog.redact(data)
    assert out["password"] == out["Authorization"] == out["x-platform-key"] == "****"
    assert out["nested"]["token"] == out["nested"]["FOUNDRY_KEY"] == "****"
    assert out["nested"]["list"][0] == {"cookie": "****", "keep": 1}
    assert out["database_url"] == "****" and out["ACS_CONNECTION_STRING"] == "****"
    assert out["ok"] == "fine"
    assert data["password"] == "p"  # original untouched


def test_redact_scrubs_key_value_patterns_in_strings() -> None:
    s = "connecting Server=tcp:x;Password=Hunter2;Encrypt=yes and token=abc123 done"
    out = applog.redact(s)
    assert "Hunter2" not in out and "abc123" not in out
    assert "Password=****" in out


def test_logger_writes_json_lines_and_routes_levels(capsys: pytest.CaptureFixture[str]) -> None:
    applog.logger.info("hello", request_id="rid-1", password="p@ss", n=1)
    applog.logger.warn("careful")
    applog.logger.error("boom", token="t")
    cap = capsys.readouterr()
    out_line = json.loads(cap.out.strip().splitlines()[-1])
    assert out_line["level"] == "info" and out_line["requestId"] == "rid-1"
    assert out_line["password"] == "****" and out_line["n"] == 1
    err_lines = [json.loads(line) for line in cap.err.strip().splitlines()]
    assert [e["level"] for e in err_lines] == ["warn", "error"]
    assert err_lines[1]["token"] == "****"
    assert "p@ss" not in cap.out + cap.err
