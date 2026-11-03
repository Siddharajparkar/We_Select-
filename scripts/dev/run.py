#!/usr/bin/env python3
"""Start the API against the real cloud services (reads api/.env.local, written by setup.py).

python scripts/dev/run.py [--check]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import API_DIR, ENV_LOCAL


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if not ENV_LOCAL.is_file():
        print("ERROR: api/.env.local not found. Run `python scripts/dev/setup.py` first.", file=sys.stderr)
        return 2
    if args.check:
        print("ok: api/.env.local present; would run `python -m app.main` in api/")
        return 0
    return subprocess.run([sys.executable, "-m", "app.main"], cwd=API_DIR, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
