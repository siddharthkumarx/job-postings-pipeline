"""Fail if any tracked file is 50 MB or larger (bulk data belongs in Release assets)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

LIMIT = 50 * 1024 * 1024


def main() -> int:
    files = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True).stdout.split(
        b"\0"
    )
    big = []
    for f in files:
        if not f:
            continue
        p = Path(f.decode())
        if p.is_file() and p.stat().st_size >= LIMIT:
            big.append(f"{p} {p.stat().st_size / 1e6:.1f} MB")
    if big:
        print("Files at or over 50 MB:\n" + "\n".join(big))
        return 1
    print(f"all {len(files) - 1} tracked files under 50 MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
