"""Daily run, backfill, rebuild and release-hold (docs/architecture.md).

Exit codes: 0 = published, 2 = held (quality gate), 1 = failed.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import traceback
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from jobpipe import fx, guards, ingest, publish, state, warehouse
from jobpipe.models import SCHEMA_VERSION

log = logging.getLogger("jobpipe")

PIPELINE_START = date(2026, 11, 1)  # first month that can hold bronze releases


@dataclass
class Paths:
    data_dir: Path = Path("data")
    public_dir: Path = Path("public")
    site_dir: Path = Path("site")
    seeds_dir: Path = Path("seeds")
    duckdb: Path = field(default_factory=lambda: Path("data/warehouse.duckdb"))

    @property
    def boards_csv(self) -> Path:
        return self.seeds_dir / "boards.csv"


@dataclass
class Outcome:
    status: str  # published | held | failed
    entry: dict[str, Any]

    @property
    def exit_code(self) -> int:
        return {"published": 0, "held": 2}.get(self.status, 1)


def _months(start: date, end: date) -> list[str]:
    out, cur = [], start.replace(day=1)
    while cur <= end:
        out.append(f"{cur:%Y-%m}")
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _vars(d_from: date | None, d_to: date | None) -> dict[str, Any]:
    return {
        "run_from": d_from.isoformat() if d_from else "",
        "run_to": d_to.isoformat() if d_to else "",
    }


def restore(gh: state.GitHubReleases, paths: Paths, before: date) -> tuple[dict[str, Any], bool]:
    """Restore the last good warehouse, or download all earlier bronze for a rebuild.

    Returns (state, full_refresh_needed).
    """
    st = state.pull_warehouse(gh, paths.duckdb)
    if st is not None:
        problems = state.validate_warehouse(paths.duckdb, list(st.get("bronze_dates", [])))
        if not problems:
            return st, False
        log.warning("warehouse snapshot unusable (%s): rebuilding from bronze assets", problems)
        paths.duckdb.unlink(missing_ok=True)
    else:
        log.warning("no warehouse snapshot: rebuilding from bronze assets")
    dates = [d for d in state.bronze_dates(gh, _months(PIPELINE_START, before)) if d < before]
    for d in dates:
        state.pull_bronze(gh, paths.data_dir, d)
    return {"bronze_dates": [d.isoformat() for d in dates]}, True


def unpublished_dates(gh: state.GitHubReleases, st: dict[str, Any], before: date) -> list[date]:
    """Stored bronze days after the last published snapshot, before ``before``, oldest first.

    These are the held runs (and runs that failed after storing bronze): their bronze is in
    the releases, but the snapshot never loaded them because only published runs upload one.
    """
    loaded = set(st.get("bronze_dates", []))
    last = st.get("last_good_run") or max(loaded, default=None)
    since = date.fromisoformat(last) if last else PIPELINE_START - timedelta(days=1)
    return [
        d
        for d in state.bronze_dates(gh, _months(since, before))
        if since < d < before and d.isoformat() not in loaded
    ]


def load_unpublished(
    gh: state.GitHubReleases,
    paths: Paths,
    st: dict[str, Any],
    before: date,
    notes: list[str],
    *,
    fx: bool = True,
) -> list[date]:
    """Download every unpublished day since the snapshot, once each, in date order.

    The days join this build's window and ``st["bronze_dates"]``, so the next snapshot lists
    them and they are never loaded twice. ``fx=False`` keeps the FX file this run fetched.
    Returns the days loaded.
    """
    loaded: list[date] = []
    for d in unpublished_dates(gh, st, before):
        if state.pull_bronze(gh, paths.data_dir, d, fx=fx):
            loaded.append(d)
        else:  # never build on half a day: absences would count without the board log
            state.drop_bronze_local(paths.data_dir, d)
            notes.append(f"bronze for {d} incomplete; not loaded")
    if loaded:
        notes.append("loaded unpublished days " + ", ".join(d.isoformat() for d in loaded))
        st["bronze_dates"] = sorted({*st.get("bronze_dates", []), *(d.isoformat() for d in loaded)})
    return loaded


def _fx(gh: state.GitHubReleases | None, paths: Paths, notes: list[str]) -> None:
    try:
        info = fx.fetch(paths.data_dir)
        notes.append(f"fx latest {info['latest_rate_date']}")
    except Exception as exc:  # keep running on the previous rates
        notes.append(f"fx fetch failed ({exc}); using previous rates")
        if not fx.fx_path(paths.data_dir).exists():
            raise


def publish_all(
    paths: Paths, run_date: date, gh: state.GitHubReleases | None, notes: list[str]
) -> None:
    publish.summary_csvs(paths.duckdb, paths.public_dir / "summary")
    publish.readme_extracts(paths.duckdb, paths.public_dir)
    tables = publish.export_tables(paths.duckdb, paths.data_dir / "public")
    notes.append("tables " + ", ".join(f"{k}={v}" for k, v in tables.items()))
    month_file = publish.monthly_dataset(
        paths.duckdb, run_date.replace(day=1), paths.data_dir / "dataset"
    )
    if gh is not None:
        gh.upload(state.dataset_tag(run_date), month_file)
        gh.mark_latest(state.dataset_tag(run_date))
        gh.upload(
            state.dataset_tag(run_date),
            paths.data_dir / "public" / "dim_company.parquet",
            f"dim_company_{run_date:%Y-%m}.parquet",
        )
    notes.append("hf " + publish.hf_upload([month_file]))
    try:
        from jobpipe.site import build as site_build

        site_build.build(paths.duckdb, paths.public_dir, paths.site_dir)
    except ImportError:
        notes.append("site module missing")
    docs = warehouse.run_dbt(
        ["docs", "generate", "--static"],
        data_dir=paths.data_dir,
        duckdb_path=paths.duckdb,
        seeds_dir=paths.seeds_dir,
    )
    static = warehouse.DBT_DIR / "target" / "static_index.html"
    if docs.success and static.exists():
        (paths.site_dir / "dbt-docs").mkdir(parents=True, exist_ok=True)
        shutil.copy(static, paths.site_dir / "dbt-docs" / "index.html")
    else:
        notes.append("dbt docs generation failed")


def _finish(
    paths: Paths, entry: dict[str, Any], status: str, t0: float, today: date | None = None
) -> Outcome:
    entry["status"] = status
    entry["finished_at"] = _now()
    entry["duration_s"] = round(time.monotonic() - t0, 1)
    publish.append_run(paths.public_dir / "runs.jsonl", entry)
    publish.write_status(paths.public_dir, today)
    if status == "published" and (paths.site_dir / "index.html").exists():
        # The dashboard was first built before this run was logged; build it again so its
        # status line and run count include this run. A failure keeps the first build.
        try:
            from jobpipe.site import build as site_build

            site_build.build(paths.duckdb, paths.public_dir, paths.site_dir)
        except Exception as exc:
            log.warning("dashboard re-render skipped: %s: %s", type(exc).__name__, exc)
    return Outcome(status, entry)


def build_and_gate(
    paths: Paths,
    run_date: date,
    st: dict[str, Any],
    full_refresh: bool,
    vars_: dict[str, Any],
    entry: dict[str, Any],
    notes: list[str],
    gh: state.GitHubReleases | None,
    force: bool = False,
) -> str:
    args = ["build", "--full-refresh"] if full_refresh else ["build"]
    res = warehouse.run_dbt(
        args,
        data_dir=paths.data_dir,
        duckdb_path=paths.duckdb,
        seeds_dir=paths.seeds_dir,
        vars_={} if full_refresh else vars_,
    )
    entry["dbt"] = res.counts
    reasons: list[str] = [f"dbt: {f}" for f in res.failures[:10]]
    stats: guards.RunStats | None = None
    if res.success:
        stats = guards.collect(paths.duckdb, run_date)
        entry.update(
            {
                "boards": stats.boards_total,
                "boards_ok": stats.boards_ok,
                "postings_listed": stats.postings_listed,
                "open_postings": stats.open_postings,
                "new_postings": stats.new_postings,
                "closed_postings": stats.closed_postings,
                "reopened_postings": stats.reopened_postings,
                "first_fetch_postings": stats.first_fetch_postings,
                "open_previous": stats.open_previous,
                "us_share": round(stats.us_share, 4),
                "salary_share": round(stats.salary_share, 4),
                "companies": stats.boards_total,
            }
        )
        reasons += guards.evaluate(stats, st.get("last_good_stats"))
        note = stats.flow_note()  # a note, not a hold: the run itself is still sound
        if note:
            notes.append(note)
    entry["hold_reasons"] = reasons
    if reasons and not force:
        return "held"
    assert stats is not None
    publish_all(paths, run_date, gh, notes)
    # A day without postings (every board failed) leaves no rows in silver.stg_postings, so the
    # snapshot must not list it: validate_warehouse would refuse every later upload.
    loaded = [
        d
        for d in sorted({*st.get("bronze_dates", []), run_date.isoformat()})
        if state.bronze_postings_rows(paths.data_dir, date.fromisoformat(d)) != 0
    ]
    new_state = {
        "last_good_run": run_date.isoformat(),
        "last_good_stats": stats.as_dict(),
        "bronze_dates": loaded,
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
    }
    if gh is not None:
        state.push_warehouse(gh, paths.duckdb, new_state)
    return "published"


def daily(
    run_date: date, paths: Paths | None = None, gh: state.GitHubReleases | None = None
) -> Outcome:
    paths = paths or Paths()
    t0 = time.monotonic()
    entry: dict[str, Any] = {
        "run_date": run_date.isoformat(),
        "kind": "daily",
        "started_at": _now(),
        "git_sha": os.environ.get("GITHUB_SHA", "")[:12],
        "actions_run_id": os.environ.get("GITHUB_RUN_ID", ""),
    }
    notes: list[str] = []
    entry["notes"] = notes
    try:
        gh = gh or state.GitHubReleases()
        st, full_refresh = restore(gh, paths, run_date)
        if full_refresh:
            notes.append(f"rebuilt warehouse from {len(st.get('bronze_dates', []))} bronze dates")
        manifest = ingest.run(run_date, boards_csv=paths.boards_csv, data_dir=paths.data_dir)
        entry["ingest"] = {
            k: manifest[k]
            for k in ("boards", "boards_ok", "postings", "invalid_postings", "duration_s")
        }
        entry["ingest"]["spot_check"] = manifest.get("spot_check", {})
        entry["ingest"]["requests"] = sum(h.get("requests", 0) for h in manifest["http"].values())
        entry["ingest"]["blocked_hosts"] = [
            h for h, s in manifest["http"].items() if s.get("blocked")
        ]
        _fx(gh, paths, notes)
        state.push_bronze(gh, paths.data_dir, run_date)
        # Catch up on held days only once today's bronze is stored: the APIs cannot show the
        # past, so a failed download must never cost today's data. Keep today's FX file.
        catch_up = (
            [] if full_refresh else load_unpublished(gh, paths, st, run_date, notes, fx=False)
        )
        window = _vars(min([*catch_up, run_date]), run_date)
        status = build_and_gate(paths, run_date, st, full_refresh, window, entry, notes, gh)
    except Exception as exc:
        entry["error"] = f"{type(exc).__name__}: {exc}"[:500]
        entry["traceback"] = traceback.format_exc()[-2000:]
        status = "failed"
    return _finish(paths, entry, status, t0, run_date)


def backfill(
    d_from: date,
    d_to: date,
    paths: Paths | None = None,
    gh: state.GitHubReleases | None = None,
    force: bool = False,
) -> Outcome:
    """Re-process stored bronze snapshots for a date range (the APIs cannot show the past)."""
    paths = paths or Paths()
    t0 = time.monotonic()
    entry: dict[str, Any] = {
        "run_date": d_to.isoformat(),
        "kind": "backfill" if not force else "release-hold",
        "range": [d_from.isoformat(), d_to.isoformat()],
        "started_at": _now(),
        "git_sha": os.environ.get("GITHUB_SHA", "")[:12],
    }
    notes: list[str] = []
    entry["notes"] = notes
    try:
        gh = gh or state.GitHubReleases()
        st, full_refresh = restore(gh, paths, d_from)
        catch_up = [] if full_refresh else load_unpublished(gh, paths, st, d_from, notes)
        found: list[str] = []
        missing: list[str] = []
        d = d_from
        while d <= d_to:
            (found if state.pull_bronze(gh, paths.data_dir, d) else missing).append(d.isoformat())
            d += timedelta(days=1)
        entry["dates_found"], entry["dates_missing"] = found, missing
        if not found:
            raise RuntimeError("no bronze snapshots in range")
        last = date.fromisoformat(found[-1])
        entry["run_date"] = last.isoformat()
        st["bronze_dates"] = sorted({*st.get("bronze_dates", []), *found})
        window = _vars(min([*catch_up, d_from]), d_to)
        status = build_and_gate(
            paths, last, st, full_refresh, window, entry, notes, gh, force=force
        )
    except Exception as exc:
        entry["error"] = f"{type(exc).__name__}: {exc}"[:500]
        entry["traceback"] = traceback.format_exc()[-2000:]
        status = "failed"
    return _finish(paths, entry, status, t0)


def rebuild(paths: Paths | None = None, gh: state.GitHubReleases | None = None) -> Outcome:
    """Drop the warehouse and replay every bronze snapshot (full refresh)."""
    paths = paths or Paths()
    gh = gh or state.GitHubReleases()
    today = datetime.now(UTC).date()
    dates = state.bronze_dates(gh, _months(PIPELINE_START, today))
    if not dates:
        raise RuntimeError("no bronze snapshots to rebuild from")
    paths.duckdb.unlink(missing_ok=True)
    t0 = time.monotonic()
    entry: dict[str, Any] = {
        "run_date": dates[-1].isoformat(),
        "kind": "rebuild",
        "started_at": _now(),
        "git_sha": os.environ.get("GITHUB_SHA", "")[:12],
    }
    notes: list[str] = []
    entry["notes"] = notes
    try:
        for d in dates:
            state.pull_bronze(gh, paths.data_dir, d)
        st = {"bronze_dates": [d.isoformat() for d in dates]}
        status = build_and_gate(paths, dates[-1], st, True, {}, entry, notes, gh)
    except Exception as exc:
        entry["error"] = f"{type(exc).__name__}: {exc}"[:500]
        status = "failed"
    return _finish(paths, entry, status, t0)


def offline_build(paths: Paths) -> warehouse.DbtResult:
    """dbt build on synthetic fixtures (CI): no network, no GitHub."""
    from jobpipe import fixtures

    fixtures.write(paths.data_dir, paths.seeds_dir)
    return warehouse.run_dbt(
        ["build"], data_dir=paths.data_dir, duckdb_path=paths.duckdb, seeds_dir=paths.seeds_dir
    )


def dump(outcome: Outcome) -> str:
    keep = {k: v for k, v in outcome.entry.items() if k != "traceback"}
    return json.dumps(keep, indent=2, default=str)
