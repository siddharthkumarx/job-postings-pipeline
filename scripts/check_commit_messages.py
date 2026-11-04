"""Fail if any commit message breaks the rule in scripts/commit_guard.py.

Used by CI (job `commit-messages`). Checks every commit reachable from HEAD, so the clone
must have full history (fetch-depth: 0).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from commit_guard import problems


def main() -> int:
    out = subprocess.run(
        ["git", "log", "--format=%H%x00%B%x01"], check=True, capture_output=True, text=True
    ).stdout
    bad: list[str] = []
    for record in out.split("\x01"):
        record = record.strip("\n")
        if not record:
            continue
        sha, _, body = record.partition("\x00")
        bad += [f"{sha[:12]}: {p}" for p in problems(body)]
    if bad:
        print("Commit messages must have no trailers except Signed-off-by and no footer:")
        print("\n".join(bad))
        return 1
    print("commit messages OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
