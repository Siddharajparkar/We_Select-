#!/usr/bin/env python3
"""Live checks for phases 0 to 6 against a running server (local `run.py` or the deployed API).

python scripts/dev/verify.py [--base-url http://127.0.0.1:8080] [--upto 6] [--no-ai]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ENV_LOCAL, REPO_ROOT, parse_env_file


def build_command(base_url: str, upto: int, with_ai: bool) -> list[str]:
    local = base_url.startswith(("http://127.0.0.1", "http://localhost"))
    return [
        sys.executable, str(REPO_ROOT / "scripts" / "e2e" / "run.py"),
        "--base-url", base_url, "--upto", str(upto), "--target", "local" if local else "azure",
        "--with-ai", "true" if with_ai else "false",
    ]  # fmt: skip


def harness_env(env_file: Path = ENV_LOCAL, base: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for the harness: hands it the platform key from api/.env.local (never printed)."""
    env = dict(os.environ if base is None else base)
    if "E2E_PLATFORM_KEY" not in env and env_file.is_file():
        from_file = parse_env_file(env_file).get("PLATFORM_KEY", "")
        if from_file:
            env["E2E_PLATFORM_KEY"] = from_file
    return env


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument("--upto", type=int, default=6)
    ap.add_argument("--no-ai", action="store_true", help="skip the checks that call the real AI model")
    args = ap.parse_args(argv)
    return subprocess.run(
        build_command(args.base_url, args.upto, not args.no_ai), check=False, env=harness_env()
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
