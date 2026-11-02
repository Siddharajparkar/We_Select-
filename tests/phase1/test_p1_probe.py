"""Phase 1: the Azure connectivity probe (offline parts) - masking, config probe, URL building."""

from __future__ import annotations

import pytest

from app.tools import probe

BASE_ENV = {
    "APP_ENV": "test", "REPO_BACKEND": "memory", "FILES_MODE": "memory", "AI_MODE": "fake", "EMAIL_MODE": "fake",
    "DATABASE_URL": "Server=localhost;Database=test;User ID=sa;Password=x;",
    "SESSION_SECRET": "test-secret-at-least-32-chars-long-x", "PLATFORM_KEY": "test-platform-at-least-32-chars-long-x",
    "BLOB_CONNECTION_STRING": "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=ZmFrZQ==;",
    "BLOB_CONTAINER": "jd-files", "APP_BASE_URL": "http://localhost:8080", "API_INTERNAL_URL": "http://localhost:8080",
}  # fmt: skip


def test_mask_secret_keeps_four_chars() -> None:
    assert probe.mask_secret("abcdefgh") == "abcd****"
    assert probe.mask_secret("abc") == "****"
    assert probe.mask_secret("") == "****"
    assert probe.mask_secret(None) == "****"


def test_config_probe_passes_with_all_vars() -> None:
    r = probe.probe_config(BASE_ENV)
    assert (r.name, r.status) == ("config", "PASS")


@pytest.mark.parametrize("missing", ["DATABASE_URL", "SESSION_SECRET", "PLATFORM_KEY", "BLOB_CONNECTION_STRING"])
def test_config_probe_fails_and_names_the_missing_variable(missing: str) -> None:
    env = {k: v for k, v in BASE_ENV.items() if k != missing}
    r = probe.probe_config(env)
    assert r.status == "FAIL" and missing in r.reason


def test_config_probe_requires_foundry_vars_in_azure_ai_mode() -> None:
    r = probe.probe_config({**BASE_ENV, "AI_MODE": "azure"})
    assert r.status == "FAIL" and "FOUNDRY_ENDPOINT" in r.reason and "FOUNDRY_KEY" in r.reason


def test_config_probe_requires_acs_vars_in_azure_email_mode() -> None:
    r = probe.probe_config({**BASE_ENV, "EMAIL_MODE": "azure"})
    assert r.status == "FAIL" and "ACS_CONNECTION_STRING" in r.reason


def test_config_probe_output_never_prints_values(capsys: pytest.CaptureFixture[str]) -> None:
    probe.probe_config(BASE_ENV)
    out = capsys.readouterr().out
    assert "present" in out and "test-secret-at-least" not in out and "ZmFrZQ" not in out


@pytest.mark.parametrize(
    ("style", "version", "expected"),
    [
        ("v1", "", "https://res.openai.azure.com/openai/v1/chat/completions"),
        ("v1", "2024-10-21", "https://res.openai.azure.com/openai/v1/chat/completions"),  # v1 never sends api-version
        ("azure-deployments", "", "https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions"),
        ("azure-deployments", "2024-10-21",
         "https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-10-21"),
    ],
)  # fmt: skip
def test_foundry_url_follows_api_style(style: str, version: str, expected: str) -> None:
    assert probe.foundry_url("https://res.openai.azure.com/", "gpt-4o", style, version) == expected


def test_missing_prerequisites_fail_fast_without_network() -> None:
    assert probe.probe_sql({}).status == "FAIL"
    assert probe.probe_blob({}).status == "FAIL"
    assert probe.probe_foundry({}).status == "FAIL"
    assert probe.probe_acs("a@b.invalid", {}).status == "FAIL"


def test_insights_is_skipped_when_unset_and_acs_skipped_without_recipient() -> None:
    assert probe.probe_insights({}).status == "SKIP"
    assert probe.probe_acs(None, {}).status == "SKIP"


def test_foundry_probe_sends_api_key_header_and_reports_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    seen: dict[str, object] = {}

    def fake_post(url: str, headers: dict[str, str], json: dict[str, object], timeout: int) -> httpx.Response:
        seen.update(url=url, headers=headers, body=json, timeout=timeout)
        return httpx.Response(200, json={"usage": {"total_tokens": 17}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    env = {"FOUNDRY_ENDPOINT": "https://r.example", "FOUNDRY_KEY": "supersecretkey", "FOUNDRY_DEPLOYMENT": "gpt-4o"}
    r = probe.probe_foundry(env)
    assert r.status == "PASS" and "tokens=17" in r.reason and "style=v1" in r.reason
    assert seen["url"] == "https://r.example/openai/v1/chat/completions"
    assert seen["headers"]["api-key"] == "supersecretkey"  # type: ignore[index]
    assert seen["timeout"] == 30
    assert "supersecretkey" not in r.reason


def test_foundry_probe_failure_reports_status_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    def fake_post(url: str, **_: object) -> httpx.Response:
        return httpx.Response(401, text="bad key=supersecretkey", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    r = probe.probe_foundry(
        {"FOUNDRY_ENDPOINT": "https://r", "FOUNDRY_KEY": "supersecretkey", "FOUNDRY_DEPLOYMENT": "d"}
    )
    assert r.status == "FAIL" and "HTTP 401" in r.reason and "supersecretkey" not in r.reason


def test_main_prints_summary_and_exit_codes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for k, v in BASE_ENV.items():
        monkeypatch.setenv(k, v)
    assert probe.main(["config"]) == 0
    out = capsys.readouterr().out
    assert "PROBE CONFIG PASS" in out and "PROBE ALL PASS (1 passed, 0 failed, 0 skipped)" in out
    monkeypatch.delenv("DATABASE_URL")
    assert probe.main(["config"]) == 1
    assert "PROBE ALL FAIL" in capsys.readouterr().out
    assert probe.main(["nonsense"]) == 2


def test_acs_is_never_part_of_all(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    for name in ("sql", "blob", "foundry", "insights"):
        monkeypatch.setattr(probe, f"probe_{name}", lambda name=name: probe.ProbeResult(name, "PASS", 1, "stub"))
    monkeypatch.setattr(probe, "probe_config", lambda: probe.ProbeResult("config", "PASS", 1, "stub"))
    called: list[str] = []
    monkeypatch.setattr(probe, "probe_acs", lambda to: called.append(to) or probe.ProbeResult("acs", "PASS", 1, ""))
    assert probe.main(["all"]) == 0
    assert called == []
    assert "PROBE ACS" not in capsys.readouterr().out
