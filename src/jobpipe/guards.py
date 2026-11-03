"""Run-level quality guards (docs/decisions.md D-012).

``collect`` measures the run from the warehouse; ``evaluate`` compares it with
the last published run and returns the reasons to hold (empty = publish).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

MAX_OPEN_CHANGE = 0.35
MIN_BOARDS_OK_SHARE = 0.90
NULL_LIMITS = {
    "title_null": 0.0,
    "job_url_null": 0.0,
    "company_null": 0.0,
    "location_null": 0.10,
    "role_other": 0.40,
    "country_unknown": 0.25,
}


@dataclass(frozen=True, slots=True)
class RunStats:
    run_date: str
    boards_total: int
    boards_ok: int
    postings_listed: int
    open_postings: int
    new_postings: int
    closed_postings: int
    title_null: float
    job_url_null: float
    company_null: float
    location_null: float
    role_other: float
    country_unknown: float
    us_share: float
    salary_share: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def collect(duckdb_path: Path, run_date: date) -> RunStats:
    import duckdb

    d = run_date.isoformat()
    con = duckdb.connect(str(duckdb_path))
    try:
        b = con.execute(
            "select count(*), count(*) filter (where status = 'ok') "
            "from silver.stg_board_runs where run_date = ?",
            [d],
        ).fetchone()
        q = con.execute(
            """
            select
                count(*) as n,
                avg(case when d.title is null or d.title = '' then 1 else 0 end),
                avg(case when d.job_url is null then 1 else 0 end),
                avg(case when f.company_name is null then 1 else 0 end),
                avg(case when d.location_raw is null then 1 else 0 end),
                avg(case when d.role_family = 'other' then 1 else 0 end),
                avg(case when d.country_code is null then 1 else 0 end),
                avg(case when d.country_code = 'US' then 1 else 0 end),
                avg(case when f.salary_min_usd_annual is not null then 1 else 0 end)
            from history.int_postings_daily d
            left join gold.fct_job_postings f using (posting_key)
            where d.run_date = ?
            """,
            [d],
        ).fetchone()
        o = con.execute(
            "select count(*) filter (where is_open), "
            "count(*) filter (where first_seen = ? and not left_censored), "
            "count(*) filter (where closed_on = ?) from gold.fct_job_postings",
            [d, d],
        ).fetchone()
    finally:
        con.close()
    assert b is not None and q is not None and o is not None
    return RunStats(
        run_date=d,
        boards_total=int(b[0]),
        boards_ok=int(b[1]),
        postings_listed=int(q[0]),
        open_postings=int(o[0]),
        new_postings=int(o[1]),
        closed_postings=int(o[2]),
        title_null=float(q[1] or 0),
        job_url_null=float(q[2] or 0),
        company_null=float(q[3] or 0),
        location_null=float(q[4] or 0),
        role_other=float(q[5] or 0),
        country_unknown=float(q[6] or 0),
        us_share=float(q[7] or 0),
        salary_share=float(q[8] or 0),
    )


def evaluate(current: RunStats, previous: dict[str, Any] | None) -> list[str]:
    reasons: list[str] = []
    if current.postings_listed == 0:
        reasons.append("no postings listed in this run")
    if current.boards_total == 0:
        reasons.append("no boards fetched")
    elif current.boards_ok / current.boards_total < MIN_BOARDS_OK_SHARE:
        reasons.append(
            f"boards fetched OK {current.boards_ok}/{current.boards_total} "
            f"< {MIN_BOARDS_OK_SHARE:.0%}"
        )
    for key, limit in NULL_LIMITS.items():
        value = getattr(current, key)
        if value > limit:
            reasons.append(f"{key} {value:.1%} > {limit:.0%}")
    if previous and previous.get("postings_listed"):
        prev = int(previous["postings_listed"])
        change = (current.postings_listed - prev) / prev
        if abs(change) > MAX_OPEN_CHANGE:
            reasons.append(
                f"postings listed changed {change:+.1%} vs last published run "
                f"({prev} → {current.postings_listed}), limit ±{MAX_OPEN_CHANGE:.0%}"
            )
    return reasons
