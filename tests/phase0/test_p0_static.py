"""Phase 0: repository hygiene and architectural guardrails (no Node, no secrets, no stray SQL)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
API_APP = REPO / "api" / "app"


NOT_OURS = {"frontend", "backend", "database", "ai_service"}  # other teams' folders: never scanned or modified here
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}


def tracked_or_present_files() -> list[Path]:
    """Files of the backend repository (git-aware when possible, plain walk in an unpacked archive)."""
    try:
        out = subprocess.run(  # noqa: S603
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],  # noqa: S607
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout.split()  # fmt: skip
        paths = [REPO / p for p in out]
    except (subprocess.CalledProcessError, FileNotFoundError):
        paths = [p for p in REPO.rglob("*") if not _SKIP_DIRS.intersection(p.relative_to(REPO).parts)]
    return [p for p in paths if p.is_file() and p.relative_to(REPO).parts[0] not in NOT_OURS]


def test_no_node_artifacts_remain() -> None:
    names = {p.name for p in tracked_or_present_files()}
    for banned in (
        "package.json",
        "package-lock.json",
        "tsconfig.json",
        ".nvmrc",
        "eslint.config.js",
        "vitest.config.ts",
    ):
        assert banned not in names, f"{banned} must not exist: the backend is Python/FastAPI only"
    ts = [p for p in tracked_or_present_files() if p.suffix in {".ts", ".mjs", ".cjs"}]
    assert ts == [], f"no JS/TS sources allowed in the backend repository content: {ts}"


def test_python_package_layout_exists() -> None:
    for rel in [
        "api/app/main.py", "api/app/config.py", "api/app/middleware.py", "api/app/core/errors.py",
        "api/app/providers/ports.py", "api/app/repositories/__init__.py", "api/app/migrations/runner.py",
        "api/app/migrations/sql/0001_init.sql", "api/app/tools/probe.py", "api/Dockerfile", "api/requirements.txt",
    ]:  # fmt: skip
        assert (REPO / rel).is_file(), rel


def test_untouchable_directories_are_unchanged_placeholders() -> None:
    """Backend-only task: frontend/, backend/ and database/ are not ours to modify.

    Opt-in (``ASSESS_CHECK_UNTOUCHED=1``): in a working copy where the owner is developing the frontend, local
    changes there are normal. The agent/CI that builds backend phases sets it.
    """
    if os.environ.get("ASSESS_CHECK_UNTOUCHED") != "1" or not (REPO / ".git").exists():
        pytest.skip("set ASSESS_CHECK_UNTOUCHED=1 inside a git checkout to enforce")
    changed = subprocess.run(  # noqa: S603
        ["git", "status", "--porcelain", "--", "frontend", "backend", "database", "ai_service"],  # noqa: S607
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    assert changed == ""


_SQL_PATTERNS = [
    re.compile(r"\bSELECT\s+.+\s+FROM\b", re.I),
    re.compile(r"\bINSERT\s+INTO\b", re.I),
    re.compile(r"\bUPDATE\s+\S+\s+SET\b", re.I),
    re.compile(r"\bDELETE\s+FROM\b", re.I),
]
_SQL_ALLOWED_DIRS = ("repositories/", "migrations/", "db/", "tools/probe.py")


def test_raw_sql_keywords_only_in_data_layer() -> None:
    offenders = []
    for f in API_APP.rglob("*.py"):
        rel = f.relative_to(API_APP).as_posix()
        if rel.startswith(_SQL_ALLOWED_DIRS):
            continue
        code = "\n".join(line for line in f.read_text().splitlines() if not line.strip().startswith(("#", '"""', "*")))
        # drop docstrings
        code = re.sub(r'""".*?"""', "", code, flags=re.S)
        if any(p.search(code) for p in _SQL_PATTERNS):
            offenders.append(rel)
    assert offenders == [], f"SQL outside repositories/migrations/db: {offenders}"


def test_engine_import_boundary() -> None:
    """Only repositories, migrations, tools and main may touch the engine/SQLAlchemy directly."""
    allowed = ("repositories/", "migrations/", "db/", "tools/", "main.py")
    offenders = []
    for f in API_APP.rglob("*.py"):
        rel = f.relative_to(API_APP).as_posix()
        if rel.startswith(allowed):
            continue
        if re.search(r"^\s*(from|import)\s+sqlalchemy", f.read_text(), re.M):
            offenders.append(rel)
    assert offenders == [], offenders


def test_no_hardcoded_secrets_in_tracked_files() -> None:
    pattern = re.compile(r"(password|secret|key|token)\s*[=:]\s*['\"]?([A-Za-z0-9+/_\-]{12,})", re.I)
    allowed_values = {"dev-only-session-secret-change-me-0000", "dev-only-platform-key-change-me-00000"}
    skip_suffix = {".pdf", ".png", ".jpg", ".zip", ".lock", ".json"}
    hits = []
    for f in tracked_or_present_files():
        if f.suffix in skip_suffix or "tests" in f.parts or f.name in {".env.example", "docker-compose.yml"}:
            continue
        if f.parts[len(REPO.parts) :][0] == "docs":
            continue
        try:
            text = f.read_text()
        except UnicodeDecodeError:
            continue
        for m in pattern.finditer(text):
            val = m.group(2)
            if val in allowed_values or val.startswith(("secrets", "env", "vars", "os.", "settings")):
                continue
            if re.match(r"^[A-Z_]+$", val) or "<" in val:
                continue
            hits.append(f"{f.relative_to(REPO)}: {m.group(0)[:50]}")
    assert hits == [], hits


def test_gitignore_covers_python_and_secrets() -> None:
    text = (REPO / ".gitignore").read_text()
    for needle in (".env", "!.env.example", "__pycache__", ".venv", ".pytest_cache", ".azure-local/", "*.pem", "*.pfx"):
        assert needle in text, needle
