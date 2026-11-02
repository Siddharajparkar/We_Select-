"""Phase 3 unit: telemetry wiring and request-context middleware internals."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from app import telemetry
from app.config import load_settings
from app.middleware import RequestContextMiddleware, resolve_request_id


def test_telemetry_is_disabled_without_connection_string() -> None:
    assert telemetry.configure_telemetry(load_settings()) is False


def test_telemetry_configures_azure_monitor_with_role_name_and_sampling(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}
    fake = types.ModuleType("azure.monitor.opentelemetry")
    fake.configure_azure_monitor = lambda **kw: calls.update(kw)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", fake)
    s = load_settings(
        APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=00000000-0000-0000-0000-000000000000",
        APPINSIGHTS_SAMPLING_PERCENT=50,
        GIT_SHA="abc",
    )
    assert telemetry.configure_telemetry(s) is True
    assert calls["sampling_ratio"] == 0.5
    attrs = calls["resource"].attributes
    assert attrs["service.name"] == "assess-api" and attrs["service.version"] == "abc"


def test_telemetry_failure_never_stops_startup(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = types.ModuleType("azure.monitor.opentelemetry")

    def boom(**_: Any) -> None:
        raise RuntimeError("bad connection string InstrumentationKey=SECRETKEY")

    fake.configure_azure_monitor = boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", fake)
    s = load_settings(APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=SECRETKEY")
    assert telemetry.configure_telemetry(s) is False
    err = capsys.readouterr().err
    assert "telemetry init failed" in err and "SECRETKEY" not in err


@pytest.mark.parametrize(
    ("incoming", "keep"),
    [
        ("abc-123", True),
        ("A.b_c-9", True),
        ("x" * 128, True),
        ("x" * 129, False),
        ("", False),
        (None, False),
        ("a b", False),
        ("a/b", False),
        ("é", False),
    ],
)
def test_resolve_request_id(incoming: str | None, keep: bool) -> None:
    out = resolve_request_id(incoming)
    assert (out == incoming) is keep
    if not keep:
        assert len(out) == 36


@pytest.mark.anyio
async def test_middleware_passes_non_http_scopes_through() -> None:
    seen: list[str] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        seen.append(scope["type"])

    mw = RequestContextMiddleware(inner, app_version="v")
    await mw({"type": "lifespan"}, None, None)  # type: ignore[arg-type]
    assert seen == ["lifespan"]


def test_middleware_adds_headers_to_every_response_start() -> None:
    import asyncio

    sent: list[dict[str, Any]] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 204, "headers": [(b"x-app-version", b"app-set")]})
        await send({"type": "http.response.body", "body": b""})

    async def send(m: dict[str, Any]) -> None:
        sent.append(m)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "GET", "path": "/api/v1/x", "headers": [(b"x-request-id", b"rid-1")]}
    asyncio.run(RequestContextMiddleware(inner, app_version="ver-9")(scope, receive, send))  # type: ignore[arg-type]
    headers = dict(sent[0]["headers"])
    assert headers[b"x-request-id"] == b"rid-1"
    assert headers[b"x-app-version"] == b"app-set", "the app's own header must not be overwritten"
    assert headers[b"x-content-type-options"] == b"nosniff" and headers[b"cache-control"] == b"no-store"


def test_middleware_converts_exceptions_after_start_without_double_response() -> None:
    import asyncio

    sent: list[dict[str, Any]] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("late failure")

    async def send(m: dict[str, Any]) -> None:
        sent.append(m)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "GET", "path": "/api/v1/x", "headers": []}
    asyncio.run(RequestContextMiddleware(inner)(scope, receive, send))  # type: ignore[arg-type]
    assert [m["type"] for m in sent] == ["http.response.start"]


def test_factory_configures_telemetry_before_building_the_fastapi_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto-instrumentation only sees apps created AFTER configure_azure_monitor ran."""
    from app import main as app_main

    order: list[str] = []
    real_fastapi = app_main.FastAPI

    def spy_cfg(settings: Any) -> bool:
        order.append("telemetry")
        return False

    def spy_app(*a: Any, **k: Any) -> Any:
        order.append("fastapi")
        return real_fastapi(*a, **k)

    monkeypatch.setattr(app_main, "configure_telemetry", spy_cfg)
    monkeypatch.setattr(app_main, "FastAPI", spy_app)
    app_main.create_app(load_settings())
    assert order == ["telemetry", "fastapi"]
