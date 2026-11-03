"""Public outputs: run ledger, status badges, summary CSVs, monthly dataset, HF upload.

Everything here reads the warehouse or ``public/runs.jsonl``; nothing is typed in
by hand, so every published number comes from a real run.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

PUBLIC_DIR = Path("public")
PUBLIC_TABLES = [
    "fct_job_postings",
    "dim_company",
    "mart_weekly_open_roles",
    "mart_days_open_bands",
    "mart_salary_bands",
    "mart_hiring_velocity",
    "mart_data_roles",
]

# Small CSVs committed to git (each well under 1 MB). Aggregates only.
SUMMARY_QUERIES: dict[str, str] = {
    "weekly_open_roles_by_family": """
        select week_start, role_family, sum(open_roles) as open_roles,
               sum(new_roles) as new_roles, sum(closed_roles) as closed_roles
        from gold.mart_weekly_open_roles group by 1, 2 order by 1, 2""",
    "weekly_open_roles_by_state": """
        select week_start, state_code, sum(open_roles) as open_roles
        from gold.mart_weekly_open_roles where country_code = 'US' and state_code <> ''
        group by 1, 2 order by 1, 2""",
    "data_roles_weekly": """
        select w.week_start, w.role_family, sum(w.open_roles) as open_roles,
               sum(w.new_roles) as new_roles, sum(w.closed_roles) as closed_roles
        from gold.mart_weekly_open_roles w
        where w.role_family in ('data_engineer','analytics_engineer','data_analyst','ml_engineer')
        group by 1, 2 order by 1, 2""",
    "data_roles_current": """
        select role_family, seniority, remote_type, count(*) as open_roles,
               count(salary_min_usd_annual) as with_salary,
               round(median((salary_min_usd_annual + salary_max_usd_annual) / 2), 0)
                   as median_salary_usd
        from gold.mart_data_roles where is_open group by 1, 2, 3 order by 1, 2, 3""",
    "salary_bands": "select * from gold.mart_salary_bands order by role_family, seniority",
    "days_open_bands": "select * from gold.mart_days_open_bands order by role_family, band_order",
    "top_companies_open_roles": """
        select company_name, provider, open_postings, open_us_postings
        from gold.dim_company order by open_postings desc, company_name limit 100""",
    "providers": """
        select provider, count(*) as companies, sum(open_postings) as open_postings,
               sum(open_us_postings) as open_us_postings
        from gold.dim_company group by 1 order by 1""",
    "remote_mix": """
        select remote_type, count(*) as open_roles
        from gold.fct_job_postings where is_open group by 1 order by 2 desc""",
}


def _connect(duckdb_path: Path) -> Any:
    import duckdb

    return duckdb.connect(str(duckdb_path))


def export_tables(duckdb_path: Path, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    con = _connect(duckdb_path)
    try:
        for t in PUBLIC_TABLES:
            path = out_dir / f"{t}.parquet"
            con.execute(f"copy gold.{t} to '{path}' (format parquet, compression zstd)")
            row = con.execute(f"select count(*) from gold.{t}").fetchone()  # noqa: S608 - constant names
            counts[t] = int(row[0]) if row else 0
    finally:
        con.close()
    return counts


def summary_csvs(duckdb_path: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    con = _connect(duckdb_path)
    try:
        for name, sql in SUMMARY_QUERIES.items():
            path = out_dir / f"{name}.csv"
            con.execute(f"copy ({sql}) to '{path}' (header, delimiter ',')")
            paths.append(path)
    finally:
        con.close()
    return paths


def monthly_dataset(duckdb_path: Path, month_start: date, out_dir: Path) -> Path:
    """Postings seen during the month (any overlap), one Parquet file."""
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    path = out_dir / f"job_postings_{month_start:%Y-%m}.parquet"
    out_dir.mkdir(parents=True, exist_ok=True)
    con = _connect(duckdb_path)
    try:
        # dates come from date objects and the path from our own data dir, not user input
        sql = (
            "copy (select * from gold.fct_job_postings "  # noqa: S608
            f"where first_seen < date '{next_month}' and last_seen >= date '{month_start}' "
            f"order by provider, board, posting_id) to '{path}' (format parquet, compression zstd)"
        )
        con.execute(sql)
    finally:
        con.close()
    return path


def hf_upload(files: list[Path], repo_id: str | None = None) -> str:
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        return "skipped: HF_TOKEN not set"
    from huggingface_hub import HfApi

    repo_id = repo_id or os.environ.get("HF_DATASET_REPO", "siddharthkumarx/us-tech-job-postings")
    api = HfApi(token=token)
    api.create_repo(repo_id, repo_type="dataset", exist_ok=True)
    for f in files:
        api.upload_file(
            path_or_fileobj=str(f),
            path_in_repo=f"data/{f.name}",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"data: update {f.name}",
        )
    return f"uploaded {len(files)} file(s) to {repo_id}"


# ---- run ledger and badges ---------------------------------------------------------------


def read_runs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_run(path: Path, entry: dict[str, Any]) -> None:
    """Append, replacing an earlier entry for the same run date (idempotent re-runs)."""
    runs = [r for r in read_runs(path) if r.get("run_date") != entry.get("run_date")]
    runs.append(entry)
    runs.sort(key=lambda r: (r.get("run_date", ""), r.get("finished_at", "")))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in runs))


def status(runs: list[dict[str, Any]], today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(UTC).date()
    if not runs:
        return {"runs": 0}
    dates = sorted(date.fromisoformat(r["run_date"]) for r in runs)
    published = sorted(
        date.fromisoformat(r["run_date"]) for r in runs if r.get("status") == "published"
    )
    first = dates[0]
    last = runs[-1]
    span_days = (max(today, dates[-1]) - first).days + 1
    published_set = set(published)
    missed = sum(1 for k in range(span_days) if (first + timedelta(days=k)) not in published_set)
    last_pub = next((r for r in reversed(runs) if r.get("status") == "published"), None)
    return {
        "first_run": first.isoformat(),
        "last_run": last["run_date"],
        "last_status": last.get("status"),
        "last_published": last_pub["run_date"] if last_pub else None,
        "days_running": span_days,
        "runs_published": len(published),
        "runs_held": sum(r.get("status") == "held" for r in runs),
        "runs_failed": sum(r.get("status") == "failed" for r in runs),
        "missed_runs": missed,
        "jobs_tracked": (last_pub or {}).get("open_postings"),
        "companies_tracked": (last_pub or {}).get("companies"),
        "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _badge(label: str, message: str, color: str) -> dict[str, Any]:
    return {"schemaVersion": 1, "label": label, "message": message, "color": color}


def write_status(public_dir: Path, today: date | None = None) -> dict[str, Any]:
    st = status(read_runs(public_dir / "runs.jsonl"), today)
    public_dir.mkdir(parents=True, exist_ok=True)
    (public_dir / "status.json").write_text(json.dumps(st, indent=2) + "\n")
    badges = public_dir / "badges"
    badges.mkdir(exist_ok=True)
    if st.get("runs", 1) == 0:
        return st
    ok = st.get("last_status") == "published"
    jobs = st.get("jobs_tracked")
    items = {
        "days-running": _badge("days running", str(st["days_running"]), "2FBFAE"),
        "last-run": _badge(
            "last run", f"{st['last_run']} {st['last_status']}", "2FBFAE" if ok else "E9A93C"
        ),
        "missed-runs": _badge(
            "missed runs", str(st["missed_runs"]), "2FBFAE" if st["missed_runs"] == 0 else "E9A93C"
        ),
        "jobs-tracked": _badge("jobs tracked", f"{jobs:,}" if jobs else "n/a", "2FBFAE"),
    }
    for name, payload in items.items():
        (badges / f"{name}.json").write_text(json.dumps(payload) + "\n")
    return st
