"""Run dbt programmatically against a data directory and DuckDB file."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DBT_DIR = Path(__file__).resolve().parents[2] / "dbt"


@dataclass(frozen=True, slots=True)
class DbtResult:
    success: bool
    failures: list[str]
    counts: dict[str, int]


def run_dbt(
    args: list[str],
    *,
    data_dir: Path,
    duckdb_path: Path,
    seeds_dir: Path = Path("seeds"),
    vars_: dict[str, Any] | None = None,
) -> DbtResult:
    from dbt.cli.main import dbtRunner

    os.environ["JOBPIPE_DATA"] = str(data_dir.resolve())
    os.environ["JOBPIPE_DUCKDB"] = str(duckdb_path.resolve())
    os.environ["JOBPIPE_SEEDS"] = str(seeds_dir.resolve())
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    cli = [*args, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)]
    if vars_:
        cli += ["--vars", json.dumps(vars_)]
    res = dbtRunner().invoke(cli)
    failures: list[str] = []
    counts: dict[str, int] = {}
    results = getattr(res.result, "results", None) or []
    for r in results:
        status = str(getattr(r, "status", "")).lower()
        counts[status] = counts.get(status, 0) + 1
        if status in ("error", "fail", "runtime error"):
            node = getattr(r, "node", None)
            name = getattr(node, "unique_id", "?") if node is not None else "?"
            failures.append(f"{name}: {status} {getattr(r, 'message', '')}"[:400])
    if res.exception is not None:
        failures.append(f"dbt exception: {res.exception}"[:400])
    return DbtResult(bool(res.success) and not failures, failures, counts)
