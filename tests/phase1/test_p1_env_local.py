"""Developer env file (api/.env.local): loaded only outside production, never overriding real env vars."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import ConfigError, env_local_file, load_settings


@pytest.fixture
def envfile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / ".env.local"
    monkeypatch.delenv("ASSESS_IGNORE_ENV_LOCAL", raising=False)
    monkeypatch.setenv("ASSESS_ENV_FILE", str(path))
    for name in ("APP_ENV", "REPO_BACKEND", "PORT", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    return path


def test_no_file_means_plain_defaults(envfile: Path) -> None:
    assert env_local_file() is None
    assert load_settings().REPO_BACKEND == "memory"


def test_file_values_are_loaded_outside_production(envfile: Path) -> None:
    envfile.write_text("PORT=9123\nUNKNOWN_KEY=ignored\n", encoding="utf-8")
    assert load_settings().PORT == 9123


def test_real_environment_wins_over_the_file(envfile: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    envfile.write_text("PORT=9123\n", encoding="utf-8")
    monkeypatch.setenv("PORT", "9555")
    assert load_settings().PORT == 9555


def test_ignore_switch_skips_the_file(envfile: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    envfile.write_text("PORT=9123\n", encoding="utf-8")
    monkeypatch.setenv("ASSESS_IGNORE_ENV_LOCAL", "1")
    assert env_local_file() is None
    assert load_settings().PORT == 8080


def test_production_environment_never_reads_the_file(envfile: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    envfile.write_text("PORT=9123\n", encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "production")
    assert env_local_file() is None


def test_a_file_that_selects_production_is_refused(envfile: Path) -> None:
    envfile.write_text("APP_ENV=production\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="never loads a local env file"):
        load_settings()
