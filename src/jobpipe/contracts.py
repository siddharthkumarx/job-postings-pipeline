"""Parse docs/data-contracts.md into {table: [(column, duckdb_type, description)]}.

The dbt contract YAML (dbt/models/marts/_marts.yml) is generated from this, and
tests/test_contracts_doc.py checks the two never drift apart.
"""

from __future__ import annotations

import re
from pathlib import Path

TYPES = {
    "VARCHAR": "varchar",
    "DATE": "date",
    "INTEGER": "integer",
    "DOUBLE": "double",
    "BOOLEAN": "boolean",
    "TIMESTAMPTZ": "timestamp with time zone",
}


def parse(path: Path = Path("docs/data-contracts.md")) -> dict[str, list[tuple[str, str, str]]]:
    sections: dict[str, list[tuple[str, str, str]]] = {}
    cur: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## (\w+)$", line)
        if m:
            cur = m.group(1)
            sections[cur] = []
            continue
        if cur and line.startswith("| ") and not line.startswith("| Column"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and re.fullmatch(r"[a-z0-9_]+", cells[0]) and cells[1] in TYPES:
                sections[cur].append((cells[0], TYPES[cells[1]], cells[2]))
    return {k: v for k, v in sections.items() if v}
