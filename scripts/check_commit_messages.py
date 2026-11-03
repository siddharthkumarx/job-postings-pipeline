"""Fail if any commit message carries tool attribution lines.

Used by CI (job `commit-messages`). Checks every commit reachable from HEAD,
so the clone must have full history (fetch-depth: 0).
"""

from __future__ import annotations

import re
import subprocess
import sys

PATTERN = re.compile(r"^\s*(co-authored-by:|session-id:)|^\W*generated with\b", re.IGNORECASE)


def main() -> int:
    out = subprocess.run(
        ["git", "log", "--format=%H%x00%B%x01"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    bad: list[str] = []
    for record in out.split("\x01"):
        record = record.strip("\n")
        if not record:
            continue
        sha, _, body = record.partition("\x00")
        for line in body.splitlines():
            if PATTERN.search(line):
                bad.append(f"{sha[:12]}: {line.strip()}")
    if bad:
        print("Commit messages must not contain attribution lines:")
        print("\n".join(bad))
        return 1
    print("commit messages OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
