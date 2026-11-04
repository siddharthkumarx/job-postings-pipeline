"""Check internal links in the repo's Markdown: relative file paths and #anchors.

External links (http, https, mailto) are not fetched. Anchors use GitHub's heading slugs.
Run: python3 scripts/check_links.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)\)|!\[[^\]]*\]\(([^)\s]+)\)")


def slug(heading: str) -> str:
    s = heading.strip().lower()
    s = re.sub(r"[`*_~]", "", s)
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    out: set[str] = set()
    seen: dict[str, int] = {}
    in_code = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_code = not in_code
        if in_code:
            continue
        m = re.match(r"^#{1,6}\s+(.*)$", line)
        if m:
            base = slug(m.group(1))
            n = seen.get(base, 0)
            out.add(base if n == 0 else f"{base}-{n}")
            seen[base] = n + 1
    return out


def main() -> int:
    files = [
        Path(p)
        for p in subprocess.run(
            ["git", "ls-files", "*.md"], check=True, capture_output=True, text=True
        ).stdout.split()
    ]
    for extra in (Path("README.md"),):
        if extra.exists() and extra not in files:
            files.append(extra)
    bad: list[str] = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for m in LINK.finditer(text):
            target = m.group(1) or m.group(2)
            if re.match(r"^(https?:|mailto:)", target):
                continue
            path_part, _, anchor = target.partition("#")
            dest = (f.parent / path_part).resolve() if path_part else f.resolve()
            if not dest.exists():
                bad.append(f"{f}: missing file {target}")
                continue
            if anchor and dest.suffix == ".md" and anchor not in anchors(dest):
                bad.append(f"{f}: missing anchor {target}")
    if bad:
        print("Broken internal links:\n" + "\n".join(bad))
        return 1
    print(f"internal links OK in {len(files)} Markdown files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
