"""Commit-message rule: no trailers except Signed-off-by, and no "Generated with" footer.

A trailer is a "Key: value" line in the last paragraph of the message when every line of
that paragraph has that shape (git's own trailer convention), e.g. "Reviewed-by: A".

    python3 scripts/commit_guard.py --fix MSGFILE   # used by .githooks/commit-msg
    python3 scripts/commit_guard.py --check MSGFILE # exit 1 if the message breaks the rule
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOWED_TRAILERS = {"signed-off-by"}
TRAILER = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*):\s+\S")
FOOTER = re.compile(r"^\W*generated with\b", re.IGNORECASE)


def _paragraphs(lines: list[str]) -> list[list[str]]:
    paras: list[list[str]] = [[]]
    for line in lines:
        if line.strip():
            paras[-1].append(line)
        elif paras[-1]:
            paras.append([])
    return [p for p in paras if p]


def _trailer_block(lines: list[str]) -> list[str]:
    paras = _paragraphs(lines)
    if len(paras) < 2:  # the subject line alone is never a trailer block
        return []
    last = paras[-1]
    return last if all(TRAILER.match(line) for line in last) else []


def problems(message: str) -> list[str]:
    lines = [ln for ln in message.splitlines() if not ln.startswith("#")]
    out = [f"footer: {ln.strip()}" for ln in lines if FOOTER.match(ln)]
    for line in _trailer_block(lines):
        m = TRAILER.match(line)
        if m and m.group(1).lower() not in ALLOWED_TRAILERS:
            out.append(f"trailer: {line.strip()}")
    return out


def clean(message: str) -> str:
    lines = [ln for ln in message.splitlines() if not FOOTER.match(ln)]
    trailers = _trailer_block([ln for ln in lines if not ln.startswith("#")])
    drop = {
        ln
        for ln in trailers
        if (m := TRAILER.match(ln)) and m.group(1).lower() not in ALLOWED_TRAILERS
    }
    kept = [ln for ln in lines if ln not in drop]
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept) + "\n"


def main(argv: list[str]) -> int:
    mode, path = argv[1], Path(argv[2])
    text = path.read_text(encoding="utf-8")
    if mode == "--fix":
        path.write_text(clean(text), encoding="utf-8")
        return 0
    bad = problems(text)
    for b in bad:
        print(b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
