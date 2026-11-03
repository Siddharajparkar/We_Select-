"""Shared helpers for the developer scripts: config file, Azure CLI wrapper, Key Vault secrets.

Rules: secret values are only ever passed from Key Vault to ``api/.env.local`` (or the Container App); they are
never printed, logged or put in an exception message.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "api"
ENV_LOCAL = API_DIR / ".env.local"
CONFIG_FILE = REPO_ROOT / "config" / "azure.local.env"

# Key Vault secret name -> environment variable the API reads.
SECRETS: dict[str, str] = {
    "database-url": "DATABASE_URL",
    "session-secret": "SESSION_SECRET",
    "platform-key": "PLATFORM_KEY",
    "foundry-endpoint": "FOUNDRY_ENDPOINT",
    "foundry-key": "FOUNDRY_KEY",
    "acs-connection-string": "ACS_CONNECTION_STRING",
    "acs-sender": "ACS_SENDER",
    "blob-connection-string": "BLOB_CONNECTION_STRING",
    "appinsights-connection-string": "APPLICATIONINSIGHTS_CONNECTION_STRING",
}
# Container Apps limits secret keys to 20 characters; these three Key Vault names are longer.
APP_SECRET_KEYS: dict[str, str] = {
    "acs-connection-string": "acs-conn",
    "blob-connection-string": "blob-conn",
    "appinsights-connection-string": "appi-conn",
}
PLAN_FILE = REPO_ROOT / "docs" / "PROVISIONING_PLAN.md"
REQUIRED_CONFIG = ["AZ_RESOURCE_GROUP", "AZ_KEY_VAULT", "AZ_SQL_SERVER", "AZ_APP"]

Runner = Callable[..., Any]


class DevError(Exception):
    """A problem a person can fix; the message says how."""


def parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():  # tolerate a BOM (Windows PowerShell)
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def load_config(path: Path = CONFIG_FILE) -> dict[str, str]:
    if not path.is_file():
        raise DevError(
            "config/azure.local.env not found. Copy config/azure.example.env to config/azure.local.env "
            "and fill in the real names (ask the project owner for the file)."
        )
    cfg = parse_env_file(path)
    missing = [k for k in REQUIRED_CONFIG if not cfg.get(k)]
    placeholders = [k for k, v in cfg.items() if re.fullmatch(r"<[^>]+>", v)]
    if missing:
        raise DevError(f"config/azure.local.env is missing: {', '.join(missing)}")
    if placeholders:
        raise DevError(f"config/azure.local.env still has placeholder values for: {', '.join(placeholders)}")
    return cfg


def app_secret_key(kv_name: str) -> str:
    return APP_SECRET_KEYS.get(kv_name, kv_name)


def require_signoff(plan: Path = PLAN_FILE) -> None:
    """Refuse to change Azure until a human wrote the approval line in the provisioning plan."""
    text = plan.read_text(encoding="utf-8") if plan.is_file() else ""
    if not re.search(r"^SIGN-OFF: APPROVED by ", text, re.M):
        raise DevError(
            "docs/PROVISIONING_PLAN.md has no 'SIGN-OFF: APPROVED by ...' line. "
            "The owner must review the plan and write it; nothing is changed until then."
        )


def az_executable() -> str | None:
    return shutil.which("az") or shutil.which("az.cmd")


def run_az(args: list[str], *, runner: Runner = subprocess.run, exe: str | None = None) -> str:
    """Run ``az <args>`` and return stdout. Errors carry only the last line of stderr (never the arguments)."""
    exe = exe or az_executable()
    if exe is None:
        raise DevError("Azure CLI (az) not found. Install it from https://aka.ms/installazurecli and run `az login`.")
    res = runner([exe, *args], capture_output=True, text=True, check=False)
    if res.returncode != 0:
        lines = (res.stderr or "").strip().splitlines()
        reason = lines[-1] if lines else f"exit code {res.returncode}"
        low = reason.lower()
        if "az login" in low:
            raise DevError("You are not signed in to Azure. Run `az login` in this terminal, then retry.")
        if "authorization" in low or "forbidden" in low or "does not have" in low:
            raise DevError(
                "Azure refused access. Ask the project owner to grant you the Key Vault Secrets User role "
                "(`python scripts/dev/grant_teammate.py`)."
            )
        raise DevError(f"az failed: {reason[:200]}")
    return str(res.stdout)


def kv_get(vault: str, name: str, *, runner: Runner = subprocess.run, exe: str | None = None) -> str:
    value = run_az(
        ["keyvault", "secret", "show", "--vault-name", vault, "--name", name, "--query", "value", "-o", "tsv"],
        runner=runner,
        exe=exe,
    ).strip()
    if not value:
        raise DevError(f"Key Vault secret '{name}' is empty or missing. The owner must run put_secrets.py first.")
    return value


def non_secret_settings(cfg: dict[str, str]) -> dict[str, str]:
    """Settings for a developer laptop talking to the real cloud services (no secrets here)."""
    return {
        "APP_ENV": "development",
        "REPO_BACKEND": "sql",
        "DB_SCHEMA": "assess",
        "AI_MODE": "azure",
        "EMAIL_MODE": "azure",
        "FILES_MODE": "azure",
        "FOUNDRY_API_STYLE": cfg.get("FOUNDRY_API_STYLE", "v1"),
        "FOUNDRY_DEPLOYMENT": cfg.get("FOUNDRY_DEPLOYMENT", "Phi-4-mini-instruct"),
        "BLOB_CONTAINER": cfg.get("BLOB_CONTAINER", "jd-files"),
        "COOKIE_SECURE": "false",  # plain-http local run; production refuses this
        "APP_BASE_URL": "http://localhost:8080",
        "API_INTERNAL_URL": "http://localhost:8080",
    }


def write_env_local(values: dict[str, str], path: Path = ENV_LOCAL) -> None:
    lines = ["# Generated by scripts/dev/setup.py. Gitignored. Contains secrets: never share or commit."]
    lines += [f"{k}={v}" for k, v in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
