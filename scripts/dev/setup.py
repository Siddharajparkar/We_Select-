#!/usr/bin/env python3
"""One-command developer setup.

    python scripts/dev/setup.py [--check] [--add-ip] [--skip-probes]

1. checks Python, Azure CLI sign-in and the ODBC driver;  2. reads config/azure.local.env;
3. pulls the app secrets from Key Vault into api/.env.local (values are never printed);
4. optionally adds this laptop's public IP to the SQL firewall (--add-ip, asks first);  5. runs the probes.
``--check`` only reports what it would do and changes nothing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    API_DIR,
    ENV_LOCAL,
    SECRETS,
    DevError,
    kv_get,
    load_config,
    non_secret_settings,
    run_az,
    write_env_local,
)


def check_tools() -> list[str]:
    problems: list[str] = []
    try:
        import pyodbc

        if not any("ODBC Driver 18" in d for d in pyodbc.drivers()):
            problems.append("ODBC Driver 18 for SQL Server not found (install it from Microsoft)")
    except ImportError:
        problems.append("pyodbc missing: run `pip install -r api/requirements-dev.txt`")
    return problems


def public_ip() -> str:
    import httpx

    try:
        return httpx.get("https://api.ipify.org", timeout=10).text.strip()
    except httpx.HTTPError:
        raise DevError("Could not detect your public IP. Add it in the portal: SQL server > Networking.") from None


def add_firewall_rule(cfg: dict[str, str], ip: str) -> None:
    name = "dev-" + ip.replace(".", "-")
    run_az(
        [
            "sql",
            "server",
            "firewall-rule",
            "create",
            "-g",
            cfg["AZ_RESOURCE_GROUP"],
            "-s",
            cfg["AZ_SQL_SERVER"],
            "-n",
            name,
            "--start-ip-address",
            ip,
            "--end-ip-address",
            ip,
        ]
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="report only; change nothing")
    ap.add_argument("--add-ip", action="store_true", help="offer to add this laptop's IP to the SQL firewall")
    ap.add_argument("--skip-probes", action="store_true")
    args = ap.parse_args(argv)
    try:
        problems = check_tools()
        for p in problems:
            print(f"  PROBLEM  {p}")
        cfg = load_config()
        print("  ok       config/azure.local.env")
        run_az(["account", "show", "--query", "name", "-o", "tsv"])
        print("  ok       signed in to Azure")
        if args.check:
            print(f"  would write {ENV_LOCAL.name} with {len(SECRETS)} secrets from Key Vault")
            return 1 if problems else 0
        if problems:
            return 1
        values = non_secret_settings(cfg)
        for secret, env_name in SECRETS.items():
            values[env_name] = kv_get(cfg["AZ_KEY_VAULT"], secret)
            print(f"  ok       {env_name} (from Key Vault)")
        write_env_local(values)
        print(f"  wrote    {ENV_LOCAL.name} (gitignored; not shown)")
        if args.add_ip:
            ip = public_ip()
            if input(f"Add {ip} to the SQL firewall? [y/N] ").strip().lower() == "y":
                add_firewall_rule(cfg, ip)
                print(f"  added    firewall rule for {ip}")
        if not args.skip_probes:
            return subprocess.run([sys.executable, "-m", "app.tools.probe", "all"], cwd=API_DIR, check=False).returncode
        return 0
    except DevError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
