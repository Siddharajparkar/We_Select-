"""Phase 0: configuration validation (fail fast, production refuses fakes)."""

from __future__ import annotations

import pytest

from app.config import ConfigError, load_settings

LONG = "x" * 40
PROD_OK = dict(  # noqa: C408
    APP_ENV="production", AI_MODE="azure", EMAIL_MODE="azure", FILES_MODE="azure", REPO_BACKEND="sql",
    DATABASE_URL="Server=tcp:h,1433;Database=d;User ID=u;Password=p;", SESSION_SECRET=LONG, PLATFORM_KEY=LONG,
    FOUNDRY_ENDPOINT="https://example.invalid", FOUNDRY_KEY="k", ACS_CONNECTION_STRING="endpoint=x;accesskey=y",
    ACS_SENDER="no-reply@example.invalid", BLOB_CONNECTION_STRING="UseDevelopmentStorage=true",
)  # fmt: skip


def test_defaults_are_safe_local_fakes() -> None:
    s = load_settings()
    assert (s.APP_ENV, s.REPO_BACKEND, s.AI_MODE, s.EMAIL_MODE, s.FILES_MODE) == (
        "development", "memory", "fake", "fake", "memory",
    )  # fmt: skip
    assert s.PORT == 8080 and s.DB_SCHEMA == "assess" and s.FOUNDRY_DEPLOYMENT == "gpt-4o"
    assert s.FOUNDRY_API_STYLE == "v1" and s.GIT_SHA == "local"
    assert s.BLOB_CONTAINER == "jd-files"


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("GIT_SHA", "abc123")
    monkeypatch.setenv("APPINSIGHTS_SAMPLING_PERCENT", "25")
    s = load_settings()
    assert (s.PORT, s.GIT_SHA, s.APPINSIGHTS_SAMPLING_PERCENT) == (9000, "abc123", 25.0)


def test_production_with_all_real_values_is_accepted() -> None:
    assert load_settings(**PROD_OK).is_production


@pytest.mark.parametrize("field", ["AI_MODE", "EMAIL_MODE", "FILES_MODE"])
def test_production_rejects_fake_providers(field: str) -> None:
    values = {**PROD_OK, field: "fake" if field != "FILES_MODE" else "memory"}
    with pytest.raises(ConfigError, match=f"{field} must be 'azure' in production"):
        load_settings(**values)


def test_production_rejects_memory_repo_backend() -> None:
    with pytest.raises(ConfigError, match="REPO_BACKEND must be 'sql' in production"):
        load_settings(**{**PROD_OK, "REPO_BACKEND": "memory"})


@pytest.mark.parametrize("field", ["SESSION_SECRET", "PLATFORM_KEY"])
def test_production_requires_32_char_secrets(field: str) -> None:
    with pytest.raises(ConfigError, match=f"{field} must be at least 32"):
        load_settings(**{**PROD_OK, field: "short"})


def test_production_rejects_dev_placeholder_secrets() -> None:
    with pytest.raises(ConfigError, match="placeholder"):
        load_settings(**{**PROD_OK, "SESSION_SECRET": "dev-only-" + "y" * 40})


@pytest.mark.parametrize(
    ("overrides", "needle"),
    [
        ({"REPO_BACKEND": "sql"}, "DATABASE_URL"),
        ({"AI_MODE": "azure"}, "FOUNDRY_ENDPOINT"),
        ({"EMAIL_MODE": "azure"}, "ACS_CONNECTION_STRING"),
        ({"FILES_MODE": "azurite"}, "BLOB_CONNECTION_STRING"),
    ],
)
def test_azure_modes_require_their_variables(overrides: dict[str, str], needle: str) -> None:
    with pytest.raises(ConfigError, match=needle):
        load_settings(**overrides)


def test_invalid_enum_and_port_report_field_names_not_values() -> None:
    with pytest.raises(ConfigError) as exc:
        load_settings(AI_MODE="banana", PORT=99999)
    msg = str(exc.value)
    assert "AI_MODE" in msg and "PORT" in msg
    assert "banana" not in msg


def test_config_errors_never_echo_secret_values() -> None:
    with pytest.raises(ConfigError) as exc:
        load_settings(**{**PROD_OK, "SESSION_SECRET": "tiny-secret-value"})
    assert "tiny-secret-value" not in str(exc.value)


@pytest.mark.parametrize("bad", ["", "a-b", "a b", "x]; DROP", "a.b"])
def test_db_schema_must_be_simple_identifier(bad: str) -> None:
    with pytest.raises(ConfigError, match="DB_SCHEMA"):
        load_settings(DB_SCHEMA=bad)
