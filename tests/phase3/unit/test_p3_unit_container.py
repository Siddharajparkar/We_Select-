"""Phase 3 unit: Dockerfile, .dockerignore and requirements are correct (static; the image is built only in CI)."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
API = REPO / "api"
DOCKERFILE = (API / "Dockerfile").read_text()


def test_dockerfile_is_multi_stage_python_slim() -> None:
    froms = re.findall(r"^FROM\s+(\S+)(?:\s+AS\s+(\w+))?", DOCKERFILE, re.M)
    assert [stage for _, stage in froms] == ["build", "runtime"]
    assert all(img.startswith("python:3.12-slim") for img, _ in froms)
    assert "node" not in DOCKERFILE.lower()


def test_runs_as_non_root_user() -> None:
    assert re.search(r"useradd .*--uid 10001", DOCKERFILE)
    assert re.search(r"^USER appuser$", DOCKERFILE, re.M)
    assert DOCKERFILE.index("useradd") < DOCKERFILE.index("USER appuser")


def test_exposes_8080_and_binds_port_variable() -> None:
    assert "EXPOSE 8080" in DOCKERFILE and "PORT=8080" in DOCKERFILE
    assert "APP_ENV=production" in DOCKERFILE
    cmd = DOCKERFILE.strip().splitlines()[-1]
    assert cmd.startswith("CMD") and "uvicorn app.main:create_app --factory" in cmd
    assert "--host 0.0.0.0" in cmd and "${PORT}" in cmd
    assert "--proxy-headers" in cmd, "Container Apps terminates TLS in front of us"
    assert "exec uvicorn" in cmd, "exec so SIGTERM reaches uvicorn (graceful shutdown)"
    assert "--timeout-graceful-shutdown" in cmd


def test_image_carries_git_sha_label_and_env() -> None:
    assert "ARG GIT_SHA" in DOCKERFILE
    assert "org.opencontainers.image.revision=$GIT_SHA" in DOCKERFILE
    assert re.search(r"GIT_SHA=\$GIT_SHA", DOCKERFILE)


def test_installs_sql_server_odbc_driver_18_in_runtime_stage() -> None:
    runtime = DOCKERFILE[DOCKERFILE.index("AS runtime") :]
    assert "msodbcsql18" in runtime and "ACCEPT_EULA=Y" in runtime and "unixodbc" in runtime
    assert "build-essential" not in runtime, "compilers belong in the build stage only"


def test_app_directory_including_sql_migrations_is_copied() -> None:
    assert re.search(r"^COPY app \./app$", DOCKERFILE, re.M)
    assert list(
        (API / "app" / "migrations" / "sql").glob("*.sql")
    ), "SQL migration files must exist in the image context"


def test_dockerfile_contains_no_secrets_or_latest_tags() -> None:
    assert not re.search(r"(PASSWORD|SECRET|KEY|TOKEN)\s*=\s*\S+", DOCKERFILE, re.I)
    assert ":latest" not in DOCKERFILE


def test_dockerignore_excludes_tests_envs_and_vcs() -> None:
    lines = set((API / ".dockerignore").read_text().split())
    for needle in ("tests", ".env", ".env.*", ".git", "**/__pycache__", ".pytest_cache"):
        assert needle in lines, needle
    assert "!.env.example" in lines


def test_requirements_are_bounded_and_complete() -> None:
    reqs = (API / "requirements.txt").read_text()
    for pkg in ("fastapi", "uvicorn", "pydantic", "pydantic-settings", "sqlalchemy", "pyodbc", "httpx",
                "azure-storage-blob", "azure-communication-email", "azure-monitor-opentelemetry"):  # fmt: skip
        assert re.search(rf"^{re.escape(pkg)}(\[.*\])?>=", reqs, re.M | re.I), pkg
    for line in reqs.splitlines():
        if line.strip() and not line.startswith("#"):
            assert "<" in line, f"{line} needs an upper bound so builds are reproducible within a major"
    dev = (API / "requirements-dev.txt").read_text()
    for tool in ("pytest", "ruff", "mypy", "pyyaml", "-r requirements.txt"):
        assert tool in dev


def test_no_langchain_or_node_tooling_in_runtime_requirements() -> None:
    reqs = (API / "requirements.txt").read_text().lower()
    assert "langchain" not in reqs  # only if a later agentic need appears, and then behind the AI port
    assert "express" not in reqs


def test_env_example_is_safe_and_matches_settings() -> None:
    from app.config import Settings

    text = (API / ".env.example").read_text()
    names = set(re.findall(r"^([A-Z][A-Z0-9_]+)=", text, re.M))
    assert names <= set(Settings.model_fields), f"unknown vars in .env.example: {names - set(Settings.model_fields)}"
    assert "REPO_BACKEND=memory" in text and "AI_MODE=fake" in text and "EMAIL_MODE=fake" in text
    assert not re.search(
        r"(AccountKey|Password)=(?!<|\s|$)[^\s;]{6,}", text.replace("<SET_LOCALLY>", "")
    ), "no real secrets"
