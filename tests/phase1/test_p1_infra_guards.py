"""Phase 1 (T1, no Azure): safety guards on the provisioning/discovery scripts.

Language-neutral: these scripts did not change when the backend moved to Python.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INFRA = REPO / "infra" / "azure"
SCRIPTS = [
    "10-core.sh",
    "20-sql.sh",
    "30-blob.sh",
    "40-ai.sh",
    "50-email.sh",
    "60-registry.sh",
    "70-assess-api.sh",
    "80-assess-api-config.sh",
]

FORBIDDEN = [
    r"az\s+\S+\s+keys\s+list", r"list-key\b", r"show-connection-string\b", r"get-shared-keys\b",
    r"az\s+keyvault\s+secret\s+show", r"az\s+\S+\s+exec\b", r"\baz\s+\S+\s+create\b",
    r"\baz\s+\S+\s+update\b", r"\baz\s+\S+\s+delete\b", r"\baz\s+\S+\s+set\b",
]  # fmt: skip


def code_lines(path: Path) -> str:
    return "\n".join(line for line in path.read_text().splitlines() if not line.strip().startswith("#"))


# ── inventory.sh is read-only ──────────────────────────────────────────────────────────────
INVENTORY = INFRA / "discovery" / "inventory.sh"


def test_inventory_script_exists() -> None:
    assert INVENTORY.is_file()


@pytest.mark.parametrize("pattern", FORBIDDEN)
def test_inventory_has_no_state_changing_or_secret_revealing_verbs(pattern: str) -> None:
    assert not re.search(pattern, code_lines(INVENTORY)), f"inventory.sh must stay read-only ({pattern})"


# ── sign-off gate ──────────────────────────────────────────────────────────────────────────
def test_run_wrapper_enforces_signoff_on_the_plan() -> None:
    text = (INFRA / "_run.sh").read_text()
    assert "PROVISIONING_PLAN.md" in text
    assert re.search(r"SIGN-OFF: APPROVED by", text)
    assert "exit 1" in text
    assert 'DRY_RUN="${DRY_RUN:-1}"' in text, "dry-run must be the default"


@pytest.mark.parametrize("script", SCRIPTS)
def test_every_provisioning_script_sources_the_wrapper(script: str) -> None:
    path = INFRA / script
    assert path.is_file(), script
    assert re.search(r"source.*_run\.sh", path.read_text()), f"{script} must source _run.sh"


@pytest.mark.parametrize("script", SCRIPTS)
def test_provisioning_scripts_are_strict_bash(script: str) -> None:
    text = (INFRA / script).read_text()
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text


def test_plan_is_unsigned_and_agent_never_signs_it() -> None:
    plan = (REPO / "docs" / "PROVISIONING_PLAN.md").read_text()
    assert "SIGN-OFF: <not approved>" in plan
    assert not re.search(r"^SIGN-OFF: APPROVED by", plan, re.M), "only a human may write the approval line"


def test_write_commands_are_blocked_without_signoff_even_with_dry_run_off(tmp_path: Path) -> None:
    """Behavioural check: DRY_RUN=0 + unsigned plan => exit 1 and the stubbed `az` is never asked to write."""
    stub = tmp_path / "az"
    stub.write_text('#!/bin/sh\necho "AZ_STUB $*" >> "$AZ_LOG"\n')
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "az.log"
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "DRY_RUN": "0",
        "MODE_BLOB": "create",
        "AZ_LOG": str(log),
    }
    res = subprocess.run(["bash", str(INFRA / "30-blob.sh")], env=env, capture_output=True, text=True, cwd=REPO)  # noqa: S603,S607
    assert res.returncode == 1
    assert "No sign-off found" in res.stderr
    assert not log.exists(), "no az command may run before approval"


def test_run_plan_dry_run_executes_nothing_and_succeeds(tmp_path: Path) -> None:
    stub = tmp_path / "az"
    stub.write_text('#!/bin/sh\necho "AZ_STUB $*" >> "$AZ_LOG"\n')
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "AZ_LOG": str(tmp_path / "az.log")}
    res = subprocess.run(
        ["bash", str(REPO / "scripts" / "run-plan.sh")], env=env, capture_output=True, text=True, cwd=REPO
    )  # noqa: S603,S607
    assert res.returncode == 0, res.stderr[-500:]
    assert "DRY-RUN" in res.stdout and "[EXEC]" not in res.stdout and " EXEC]" not in res.stdout
    assert not (tmp_path / "az.log").exists()


def test_reuse_and_budget_rules_are_documented_in_the_scripts() -> None:
    api = (INFRA / "70-assess-api.sh").read_text()
    assert "assess-api" in api and "--target-port 8080" in api
    assert "Portal apps are never modified" in api


def test_no_real_azure_identifiers_in_public_repo_scripts() -> None:
    guid = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
    for f in list(INFRA.glob("*.sh")) + list((INFRA / "discovery").glob("*")):
        assert not guid.search(f.read_text()), f"{f.name}: subscription/tenant ids must not be committed"


# ── assess-api container app shape (T1: static; semantics UNVERIFIED until OC-1F) ──────────
def _app_yaml() -> dict:
    import yaml

    return yaml.safe_load((INFRA / "assess-api.containerapp.yaml").read_text())


def test_containerapp_yaml_matches_budget_and_single_replica() -> None:
    props = _app_yaml()["properties"]
    c = props["template"]["containers"][0]
    assert c["resources"] == {"cpu": 0.25, "memory": "0.5Gi"}
    assert props["template"]["scale"] == {"minReplicas": 1, "maxReplicas": 1}
    assert props["configuration"]["activeRevisionsMode"] == "Single"
    assert props["configuration"]["ingress"]["external"] is True
    assert props["configuration"]["ingress"]["targetPort"] == 8080


def test_containerapp_yaml_probes_hit_health() -> None:
    probes = {p["type"]: p for p in _app_yaml()["properties"]["template"]["containers"][0]["probes"]}
    assert set(probes) == {"Startup", "Readiness", "Liveness"}
    for p in probes.values():
        assert p["httpGet"] == {"path": "/api/v1/health", "port": 8080}
    assert probes["Startup"]["periodSeconds"] * probes["Startup"]["failureThreshold"] >= 60


def test_containerapp_yaml_has_no_inline_secret_values() -> None:
    env = {e["name"]: e for e in _app_yaml()["properties"]["template"]["containers"][0]["env"]}
    for name in (
        "DATABASE_URL",
        "SESSION_SECRET",
        "PLATFORM_KEY",
        "FOUNDRY_KEY",
        "ACS_CONNECTION_STRING",
        "BLOB_CONNECTION_STRING",
    ):
        assert "secretRef" in env[name] and "value" not in env[name], name
    assert env["APP_ENV"]["value"] == "production"
    text = (INFRA / "assess-api.containerapp.yaml").read_text()
    assert "<ACR>" in text and not re.search(r"\.azurecr\.io/assess-api:[0-9a-f]{7,}", text)


def test_config_script_is_dry_run_by_default_and_only_targets_assess_api() -> None:
    out = subprocess.run(
        ["bash", str(INFRA / "80-assess-api-config.sh")],
        capture_output=True,
        text=True,
        env={**os.environ, "DRY_RUN": "1"},
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert "DRY-RUN" in out.stdout and "az containerapp update" in out.stdout
    assert "--yaml" in out.stdout
