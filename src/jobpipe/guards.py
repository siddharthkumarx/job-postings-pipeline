"""Run-level quality guards (docs/decisions.md D-012).

``collect`` measures the run from the warehouse; ``evaluate`` compares it with
the last published run and returns the reasons to hold (empty = publish).

A closing is counted in the run that confirms it (``close_confirmed_on``: the
second successful board fetch that misses the posting), never on ``closed_on``
(the first missed day, which is always one run earlier). ``flow_asof`` rebuilds
what any run saw from history alone; ``RunStats.flow_gap`` checks
open(today) = open(previous run) + new + first fetch + reopened - closed, where
"first fetch" are the left-censored postings of a board's first successful fetch.
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
    reopened_postings: int
    first_fetch_postings: int
    open_previous: int
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

    @property
    def flow_gap(self) -> int:
        """open(today) minus what the flows predict; 0 when the books balance."""
        return self.open_postings - (
            self.open_previous
            + self.new_postings
            + self.first_fetch_postings
            + self.reopened_postings
            - self.closed_postings
        )

    def flow_note(self) -> str | None:
        if self.flow_gap == 0:
            return None
        return (
            f"flow check: open {self.open_postings} != previous open {self.open_previous}"
            f" + new {self.new_postings} + first fetch {self.first_fetch_postings}"
            f" + reopened {self.reopened_postings} - closed {self.closed_postings}"
            f" (gap {self.flow_gap:+d})"
        )


# State of every posting as of two run dates ($d and $prev), from history alone: a posting
# is closed as of a date once 2 successful fetches of its board after its last listing (up to
# that date) missed it. Same rule as int_posting_lifecycle.
FLOW_SQL = """
with ok as (
    select company_id, run_date from silver.stg_board_runs where status = 'ok'
),
first_ok as (
    select company_id, min(run_date) as first_ok_run from ok group by 1
),
listed as (
    select l.posting_key, x.as_of, any_value(l.company_id) as company_id,
           min(l.run_date) as first_seen, max(l.run_date) as last_listed
    from history.int_postings_daily as l
    inner join (select $d::date as as_of union all select $prev::date) as x
        on l.run_date <= x.as_of
    group by 1, 2
),
st as (
    select s.posting_key, s.as_of, s.company_id, s.first_seen, s.last_listed,
           count(o.run_date) >= 2 as closed
    from listed as s
    left join ok as o
        on o.company_id = s.company_id and o.run_date > s.last_listed and o.run_date <= s.as_of
    group by 1, 2, 3, 4, 5
),
today as (select * from st where as_of = $d::date),
before as (select * from st where as_of = $prev::date)
select
    (select count(*) from before where not closed),
    (select count(*) from today where not closed),
    (select count(*) from today as t inner join first_ok as f using (company_id)
      where t.first_seen = $d::date and t.first_seen > f.first_ok_run),
    (select count(*) from today as t inner join first_ok as f using (company_id)
      where t.first_seen = $d::date and t.first_seen <= f.first_ok_run),
    (select count(*) from today as t inner join before as b using (posting_key)
      where t.last_listed = $d::date and b.closed),
    (select count(*) from today as t inner join before as b using (posting_key)
      where t.closed and not b.closed)
"""
FLOW_KEYS = ("open_previous", "open_now", "new", "first_fetch", "reopened", "closed")


def previous_run(con: Any, run_date: date | str) -> date | None:
    row = con.execute(
        "select max(run_date) from history.int_run_calendar where run_date < ?::date",
        [str(run_date)],
    ).fetchone()
    return row[0] if row else None


def flow_asof(con: Any, run_date: date | str) -> dict[str, int]:
    """Open / new / first-fetch / reopened / closed as the run on ``run_date`` saw them."""
    prev = previous_run(con, run_date) or date(1970, 1, 1)
    row = con.execute(FLOW_SQL, {"d": str(run_date), "prev": str(prev)}).fetchone()
    assert row is not None
    return {k: int(v) for k, v in zip(FLOW_KEYS, row, strict=True)}


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
            "count(*) filter (where close_confirmed_on = ?) from gold.fct_job_postings",
            [d, d],
        ).fetchone()
        flow = flow_asof(con, run_date)
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
        reopened_postings=flow["reopened"],
        first_fetch_postings=flow["first_fetch"],
        open_previous=flow["open_previous"],
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
