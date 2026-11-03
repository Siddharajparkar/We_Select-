#!/usr/bin/env python3
"""Point the Container App's secrets at Key Vault (references only; values never pass through this script).

    python scripts/dev/sync_secrets.py            # dry run: prints the secret names and Key Vault URLs
    python scripts/dev/sync_secrets.py --apply    # az containerapp secret set (needs the SIGN-OFF line)

The app's user-assigned identity must hold Key Vault Secrets User on the vault. Container App secret keys are
limited to 20 characters, so three long Key Vault names get short keys (see common.APP_SECRET_KEYS).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SECRETS, DevError, Runner, app_secret_key, load_config, require_signoff, run_az


def identity_resource_id(cfg: dict[str, str], *, runner: Runner) -> str:
    return run_az(
        [
            "identity",
            "show",
            "-g",
            cfg["AZ_RESOURCE_GROUP"],
            "-n",
            cfg["AZ_APP_IDENTITY"],
            "--query",
            "id",
            "-o",
            "tsv",
        ],
        runner=runner,
    ).strip()


def secret_args(vault: str, identity_id: str) -> list[str]:
    return [
        f"{app_secret_key(n)}=keyvaultref:https://{vault}.vault.azure.net/secrets/{n},identityref:{identity_id}"
        for n in SECRETS
    ]


def main(argv: list[str] | None = None, *, runner: Runner = subprocess.run) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    try:
        cfg = load_config()
        if not cfg.get("AZ_APP_IDENTITY"):
            raise DevError("AZ_APP_IDENTITY is not set in config/azure.local.env")
        if not args.apply:
            print("DRY RUN. Container App secret key -> Key Vault secret:")
            for n in SECRETS:
                print(f"  {app_secret_key(n):12} -> {n}")
            print("Re-run with --apply to write.")
            return 0
        require_signoff()
        ident = identity_resource_id(cfg, runner=runner)
        run_az(
            ["containerapp", "secret", "set", "-g", cfg["AZ_RESOURCE_GROUP"], "-n", cfg["AZ_APP"], "--secrets",
             *secret_args(cfg["AZ_KEY_VAULT"], ident), "-o", "none"], runner=runner,
        )  # fmt: skip
        print(
            f"Set {len(SECRETS)} Key Vault references on the app. Verify names:  az containerapp secret list ... --query [].name"
        )
        return 0
    except DevError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
