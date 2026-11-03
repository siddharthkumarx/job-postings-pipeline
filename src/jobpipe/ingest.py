"""Daily ingest: every tracked board → bronze Parquet for one run date.

Outputs under ``<data_dir>/bronze/``:

* ``postings/run_date=D/part-0.parquet``   - one row per posting (``models.Posting``)
* ``board_runs/run_date=D/part-0.parquet`` - one row per board (``models.BoardRun``)
* ``manifests/run_date=D.json``            - counts, HTTP stats, duration

Writing is atomic per file (temp file + rename), so a crashed run never leaves
a half-written partition that a later step could mistake for a complete one.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from jobpipe import __version__
from jobpipe.csvio import read_csv
from jobpipe.http import FetchResult, HostPolicy, PoliteClient
from jobpipe.models import PARQUET_FIELDS, SCHEMA_VERSION, BoardRun, Posting
from jobpipe.providers import get_provider
from jobpipe.providers.base import RunContext, to_postings

# Same limits as recon (docs/decisions.md D-002); Lever ≤ 1 request start per second.
HOST_POLICIES = {
    "boards-api.greenhouse.io": HostPolicy(concurrency=4, min_interval_s=0.25),
    "api.lever.co": HostPolicy(concurrency=2, min_interval_s=1.0),
    "api.ashbyhq.com": HostPolicy(concurrency=3, min_interval_s=0.35),
}

_ARROW_TYPES: dict[str, pa.DataType] = {
    "string": pa.string(),
    "list<string>": pa.list_(pa.string()),
    "bool": pa.bool_(),
    "timestamp": pa.timestamp("us", tz="UTC"),
    "double": pa.float64(),
    "int32": pa.int32(),
    "int16": pa.int16(),
    "date": pa.date32(),
}
POSTINGS_SCHEMA = pa.schema(
    [pa.field(name, _ARROW_TYPES[kind]) for name, kind in PARQUET_FIELDS],
    metadata={"schema_version": str(SCHEMA_VERSION), "writer": f"jobpipe {__version__}"},
)
BOARD_RUNS_SCHEMA = pa.schema(
    [
        ("provider", pa.string()),
        ("board", pa.string()),
        ("run_date", pa.date32()),
        ("status", pa.string()),
        ("http_status", pa.int32()),
        ("postings", pa.int32()),
        ("invalid_postings", pa.int32()),
        ("attempts", pa.int32()),
        ("elapsed_s", pa.float64()),
        ("bytes", pa.int64()),
        ("error", pa.string()),
        ("fetched_at", pa.timestamp("us", tz="UTC")),
    ]
)


@dataclass(frozen=True, slots=True)
class Board:
    provider: str
    board: str
    company: str


def load_boards(path: Path) -> list[Board]:
    return [Board(r["provider"], r["board"], r["company"]) for r in read_csv(path)]


def partition_path(data_dir: Path, table: str, run_date: date) -> Path:
    return data_dir / "bronze" / table / f"run_date={run_date.isoformat()}" / "part-0.parquet"


def _atomic_write_table(table: pa.Table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, path)


def postings_table(postings: list[Posting]) -> pa.Table:
    rows = [p.model_dump(mode="python") for p in postings]
    for r in rows:
        r["job_url"] = str(r["job_url"])
    return pa.Table.from_pylist(rows, schema=POSTINGS_SCHEMA)


def board_runs_table(runs: list[BoardRun]) -> pa.Table:
    return pa.Table.from_pylist(
        [r.model_dump(mode="python") for r in runs], schema=BOARD_RUNS_SCHEMA
    )


def _status(res: FetchResult) -> str:
    if res.ok:
        return "ok"
    if res.outcome == "not_found":
        return "not_found"
    if res.outcome == "host_blocked":
        return "blocked"
    return "error"


async def fetch_all(
    boards: list[Board], run_date: date, client: PoliteClient
) -> tuple[list[Posting], list[BoardRun]]:
    postings: list[Posting] = []
    runs: list[BoardRun] = []
    gate = asyncio.Semaphore(16)

    async def one(b: Board) -> None:
        provider = get_provider(b.provider)
        async with gate:
            res = await client.get_json(provider.board_url(b.board), provider.ingest_params())
        fetched_at = datetime.now(UTC)
        found: list[Posting] = []
        errors: list[str] = []
        if res.ok:
            found, errors = to_postings(
                provider, res.data, RunContext(b.board, run_date, fetched_at)
            )
            res.data = None  # drop descriptions now
        postings.extend(found)
        runs.append(
            BoardRun(
                provider=provider.name,  # type: ignore[arg-type]
                board=b.board,
                run_date=run_date,
                status=_status(res),  # type: ignore[arg-type]
                http_status=res.status,
                postings=len(found),
                invalid_postings=len(errors),
                attempts=res.attempts,
                elapsed_s=res.elapsed_s,
                bytes=res.bytes,
                error=(res.error or ("; ".join(errors[:3]) if errors else None)),
                fetched_at=fetched_at,
            )
        )

    await asyncio.gather(*(one(b) for b in boards))
    return postings, runs


def run(
    run_date: date,
    *,
    boards_csv: Path = Path("seeds/boards.csv"),
    data_dir: Path = Path("data"),
    client: PoliteClient | None = None,
) -> dict[str, Any]:
    boards = load_boards(boards_csv)
    t0 = time.monotonic()

    async def go() -> tuple[list[Posting], list[BoardRun], dict[str, Any]]:
        c = client or PoliteClient(host_policies=HOST_POLICIES, timeout_s=60.0)
        try:
            p, r = await fetch_all(boards, run_date, c)
            return p, r, c.stats_summary()
        finally:
            await c.aclose()

    postings, runs, http_stats = asyncio.run(go())
    postings.sort(key=lambda p: (p.provider, p.board, p.posting_id))
    runs.sort(key=lambda r: (r.provider, r.board))
    _atomic_write_table(postings_table(postings), partition_path(data_dir, "postings", run_date))
    _atomic_write_table(board_runs_table(runs), partition_path(data_dir, "board_runs", run_date))
    status_counts = Counter(f"{r.provider}:{r.status}" for r in runs)
    manifest = {
        "run_date": run_date.isoformat(),
        "boards": len(boards),
        "boards_ok": sum(r.status == "ok" for r in runs),
        "postings": len(postings),
        "invalid_postings": sum(r.invalid_postings for r in runs),
        "board_status": dict(sorted(status_counts.items())),
        "postings_by_provider": dict(Counter(p.provider for p in postings)),
        "duration_s": round(time.monotonic() - t0, 1),
        "http": http_stats,
        "schema_version": SCHEMA_VERSION,
    }
    mpath = data_dir / "bronze" / "manifests" / f"run_date={run_date.isoformat()}.json"
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
