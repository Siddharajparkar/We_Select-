"""Phase 6 unit: packaging facts that keep the image and the job loop consistent."""

from __future__ import annotations

import re
from pathlib import Path

from app.config import load_settings

ROOT = Path(__file__).resolve().parents[3]


def test_shutdown_budget_fits_the_container_apps_grace_period() -> None:
    docker = (ROOT / "api/Dockerfile").read_text()
    http_s = int(re.search(r"--timeout-graceful-shutdown (\d+)", docker).group(1))  # type: ignore[union-attr]
    yaml = (ROOT / "infra/azure/assess-api.containerapp.yaml").read_text()
    grace = int(re.search(r"terminationGracePeriodSeconds:\s*(\d+)", yaml).group(1))  # type: ignore[union-attr]
    jobs_s = load_settings().JOB_SHUTDOWN_GRACE_SECONDS
    assert http_s + jobs_s < grace, (http_s, jobs_s, grace)


def test_runtime_dependencies_for_phases_4_to_6_are_declared() -> None:
    req = (ROOT / "api/requirements.txt").read_text().lower()
    for pkg in ("argon2-cffi", "python-multipart", "pypdf", "httpx", "sqlalchemy", "pyodbc", "fastapi", "uvicorn"):
        assert pkg in req, pkg


def test_migrations_are_inside_the_image_context() -> None:
    docker = (ROOT / "api/Dockerfile").read_text()
    assert "COPY app ./app" in docker
    assert (ROOT / "api/app/migrations/sql/0003_jobs_questions_ai.sql").exists()
    assert not (ROOT / ".dockerignore").exists() or "migrations" not in (ROOT / ".dockerignore").read_text()
