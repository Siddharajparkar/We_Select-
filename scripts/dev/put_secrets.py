#!/usr/bin/env python3
"""Owner-only: fill the nine Key Vault secrets. Values are never printed.

    python scripts/dev/put_secrets.py            # dry run: shows each secret name and where its value comes from
    python scripts/dev/put_secrets.py --apply    # writes them (needs the SIGN-OFF line and Key Vault Secrets Officer)
    python scripts/dev/put_secrets.py --apply --rotate   # also replaces session-secret and platform-key

Sources: session-secret and platform-key are generated here (32 random bytes); the Foundry key, Blob, Application
Insights and ACS connection strings are read from Azure straight into Key Vault; the SQL app password is typed at a
hidden prompt; endpoint and sender are not secret. Existing secrets are kept unless a source changed (idempotent).
"""

from __future__ import annotations

import argparse
import getpass
import secrets as pysecrets
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    SECRETS,
    DevError,
    Runner,
    load_config,
    require_signoff,
    run_az,
)

SQL_APP_USER = "assess_app"
GENERATED = ("session-secret", "platform-key")


def build_database_url(server: str, db: str, password: str, user: str = SQL_APP_USER) -> str:
    if not password or any(ch in password for ch in ";{}=\"'"):
        raise DevError("The SQL password must not be empty or contain ; { } = or quote characters.")
    host = server if "." in server else f"{server}.database.windows.net"
    return (
        f"Server=tcp:{host},1433;Database={db};User ID={user};Password={password};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=90"  # 90 s: serverless DB resume after auto-pause
    )


def sources(cfg: dict[str, str]) -> dict[str, str]:
    """Human-readable origin of each secret (no values)."""
    rg = cfg["AZ_RESOURCE_GROUP"]
    return {
        "database-url": f"hidden prompt (SQL password of {SQL_APP_USER}) + server/db names from config",
        "session-secret": "generated here (32 random bytes)",
        "platform-key": "generated here (32 random bytes)",
        "foundry-endpoint": f"az cognitiveservices account show ({cfg.get('AZ_AI_RESOURCE', '?')}), not secret",
        "foundry-key": f"az cognitiveservices account keys list ({cfg.get('AZ_AI_RESOURCE', '?')}) -> Key Vault",
        "acs-connection-string": f"az communication list-key ({cfg.get('AZ_ACS', '?')}) -> Key Vault",
        "acs-sender": "ACS_SENDER from config/azure.local.env, not secret",
        "blob-connection-string": f"az storage account show-connection-string ({cfg.get('AZ_STORAGE', '?')}, rg {rg})",
        "appinsights-connection-string": f"az monitor app-insights component show ({cfg.get('AZ_APPINSIGHTS', '?')})",
    }


def read_from_azure(cfg: dict[str, str], name: str, *, runner: Runner) -> str:
    rg = cfg["AZ_RESOURCE_GROUP"]
    if name == "foundry-endpoint":
        raw = run_az(
            ["cognitiveservices", "account", "show", "-g", rg, "-n", cfg["AZ_AI_RESOURCE"],
             "--query", "properties.endpoint", "-o", "tsv"], runner=runner,
        )  # fmt: skip
        return raw.strip().rstrip("/")
    if name == "foundry-key":
        return run_az(
            ["cognitiveservices", "account", "keys", "list", "-g", rg, "-n", cfg["AZ_AI_RESOURCE"],
             "--query", "key1", "-o", "tsv"], runner=runner,
        ).strip()  # fmt: skip
    if name == "blob-connection-string":
        return run_az(
            ["storage", "account", "show-connection-string", "-g", rg, "-n", cfg["AZ_STORAGE"],
             "--query", "connectionString", "-o", "tsv"], runner=runner,
        ).strip()  # fmt: skip
    if name == "appinsights-connection-string":
        return run_az(
            ["monitor", "app-insights", "component", "show", "-g", rg, "-a", cfg["AZ_APPINSIGHTS"],
             "--query", "connectionString", "-o", "tsv"], runner=runner,
        ).strip()  # fmt: skip
    if name == "acs-connection-string":
        return run_az(
            ["communication", "list-key", "-g", rg, "--name", cfg["AZ_ACS"],
             "--query", "primaryConnectionString", "-o", "tsv"], runner=runner,
        ).strip()  # fmt: skip
    if name == "acs-sender":
        sender = cfg.get("ACS_SENDER", "")
        if not sender or sender.startswith("<"):
            raise DevError("Set ACS_SENDER in config/azure.local.env (DoNotReply@<domain>.azurecomm.net).")
        return sender
    raise DevError(f"No Azure source for {name}")


def secret_exists(vault: str, name: str, *, runner: Runner) -> bool:
    try:
        run_az(
            ["keyvault", "secret", "show", "--vault-name", vault, "--name", name, "--query", "id", "-o", "tsv"],
            runner=runner,
        )
        return True
    except DevError:
        return False


def set_secret(vault: str, name: str, value: str, *, runner: Runner) -> None:
    """Store via a private temp file so the value is never on a command line; output is suppressed."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "v"
        f.write_text(value, encoding="utf-8")
        run_az(
            ["keyvault", "secret", "set", "--vault-name", vault, "--name", name, "--file", str(f),
             "--encoding", "utf-8", "-o", "none"], runner=runner,
        )  # fmt: skip


def main(
    argv: list[str] | None = None,
    *,
    runner: Runner = subprocess.run,
    ask_password: Callable[[str], str] = getpass.getpass,
    token: Callable[[int], str] = pysecrets.token_urlsafe,
) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write to Key Vault (default is a dry run)")
    ap.add_argument("--rotate", action="store_true", help="regenerate session-secret and platform-key")
    args = ap.parse_args(argv)
    try:
        cfg = load_config()
        vault = cfg["AZ_KEY_VAULT"]
        if not args.apply:
            print(f"DRY RUN. Would write {len(SECRETS)} secrets to Key Vault '{vault}' (names only):")
            for name, origin in sources(cfg).items():
                print(f"  {name:32} <- {origin}")
            print("Re-run with --apply to write.")
            return 0
        require_signoff()
        for name in SECRETS:
            if name in GENERATED and not args.rotate and secret_exists(vault, name, runner=runner):
                print(f"  kept     {name} (already set; use --rotate to replace)")
                continue
            if name == "database-url":
                typed_value = ask_password(f"SQL password for {SQL_APP_USER} (hidden): ")
                value = build_database_url(cfg["AZ_SQL_SERVER"], cfg["AZ_SQL_DB"], typed_value)
            elif name in GENERATED:
                value = token(32)
            else:
                value = read_from_azure(cfg, name, runner=runner)
            if not value:
                raise DevError(f"Could not obtain a value for {name}.")
            set_secret(vault, name, value, runner=runner)
            print(f"  stored   {name}")
        print("Done. Verify names only:  az keyvault secret list --vault-name <KV> --query [].name -o tsv")
        return 0
    except DevError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
