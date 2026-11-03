"""Synthetic bronze for offline dbt builds (CI) - every value is made up.

Six run dates over two weeks exercise: new postings, a posting that closes
(absent from 2 successful fetches), one absent once only (stays open), one that
reopens, a title change and a salary change (SCD2), a failed board fetch that
must not count as an absence, several salary currencies/periods and locations.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from jobpipe import fx, ingest
from jobpipe.models import BoardRun, Posting

RUN_DATES = [date(2026, 10, 26) + timedelta(days=d) for d in (0, 1, 2, 7, 8, 9)]
BOARDS = [
    ("greenhouse", "acme-analytics", "Acme Analytics"),
    ("lever", "beta-robotics", "Beta Robotics"),
    ("ashby", "gamma-ai", "Gamma AI"),
]


def _p(provider: str, board: str, pid: str, title: str, d: date, **kw: Any) -> Posting:
    url = {
        "greenhouse": f"https://boards.greenhouse.io/{board}/jobs/{pid}",
        "lever": f"https://jobs.lever.co/{board}/{pid}",
        "ashby": f"https://jobs.ashbyhq.com/{board}/{pid}",
    }[provider]
    return Posting(
        provider=provider,  # type: ignore[arg-type]
        board=board,
        posting_id=pid,
        title=title,
        job_url=url,  # type: ignore[arg-type]
        run_date=d,
        fetched_at=datetime.combine(d, datetime.min.time(), UTC) + timedelta(hours=7, minutes=41),
        description_sha256="0" * 64,
        description_chars=1000,
        **kw,
    )


def postings_for(d: date) -> list[Posting]:
    i = RUN_DATES.index(d)
    out: list[Posting] = []
    # greenhouse: stable data engineer; analyst closes after day 2; SWE title changes on day 3
    out.append(
        _p(
            "greenhouse",
            "acme-analytics",
            "1001",
            "Senior Data Engineer",
            d,
            location_raw="New York, NY",
            department="Data",
            desc_salary_min=170000,
            desc_salary_max=210000,
            desc_salary_currency="USD",
            desc_salary_period="year",
        )
    )
    if i <= 2:
        out.append(
            _p(
                "greenhouse",
                "acme-analytics",
                "1002",
                "Data Analyst",
                d,
                location_raw="Remote - US",
                desc_salary_min=45,
                desc_salary_max=60,
                desc_salary_currency="USD",
                desc_salary_period="hour",
            )
        )
    out.append(
        _p(
            "greenhouse",
            "acme-analytics",
            "1003",
            "Software Engineer" if i < 3 else "Software Engineer II",
            d,
            location_raw="San Francisco, CA",
        )
    )
    if i >= 3:
        out.append(
            _p(
                "greenhouse",
                "acme-analytics",
                "1004",
                "Analytics Engineer",
                d,
                location_raw="Austin, TX",
                desc_remote_hint="hybrid",
            )
        )
    # lever: board fetch fails on day 4 (index 4) -> postings absent but not "missing"
    if i != 4:
        out.append(
            _p(
                "lever",
                "beta-robotics",
                "a1",
                "Machine Learning Engineer",
                d,
                location_raw="Pittsburgh, PA",
                workplace_type_raw="on-site",
                employment_type="Full-time",
                country_hint="US",
                api_salary_min=150000 if i < 5 else 160000,
                api_salary_max=190000,
                api_salary_currency="USD",
                api_salary_period="year",
            )
        )
        if i not in (1, 2):  # absent twice (days 1-2) then back: closes would be wrong -> reopens
            out.append(
                _p(
                    "lever",
                    "beta-robotics",
                    "a2",
                    "Firmware Engineer",
                    d,
                    location_raw="Toronto, ON",
                    country_hint="CA",
                    api_salary_min=120000,
                    api_salary_max=140000,
                    api_salary_currency="CAD",
                    api_salary_period="year",
                )
            )
    # ashby: product manager absent once (day 3) -> stays open; designer in London (GBP)
    if i != 3:
        out.append(
            _p(
                "ashby",
                "gamma-ai",
                "u-1",
                "Product Manager, Platform",
                d,
                location_raw="Seattle, WA",
                workplace_type_raw="Hybrid",
                employment_type="FullTime",
                country_hint="United States",
            )
        )
    out.append(
        _p(
            "ashby",
            "gamma-ai",
            "u-2",
            "Staff Product Designer",
            d,
            location_raw="London, United Kingdom",
            country_hint="United Kingdom",
            workplace_type_raw="Remote",
            api_salary_min=90000,
            api_salary_max=110000,
            api_salary_currency="GBP",
            api_salary_period="year",
        )
    )
    return out


def board_runs_for(d: date) -> list[BoardRun]:
    i = RUN_DATES.index(d)
    runs = []
    for provider, board, _ in BOARDS:
        failed = provider == "lever" and i == 4
        runs.append(
            BoardRun(
                provider=provider,  # type: ignore[arg-type]
                board=board,
                run_date=d,
                status="error" if failed else "ok",
                http_status=503 if failed else 200,
                postings=sum(1 for p in postings_for(d) if p.board == board),
                fetched_at=datetime.combine(d, datetime.min.time(), UTC) + timedelta(hours=8),
            )
        )
    return runs


def write(data_dir: Path, seeds_dir: Path, dates: list[date] | None = None) -> list[date]:
    dates = dates or RUN_DATES
    for d in dates:
        ingest._atomic_write_table(
            ingest.postings_table(postings_for(d)), ingest.partition_path(data_dir, "postings", d)
        )
        ingest._atomic_write_table(
            ingest.board_runs_table(board_runs_for(d)),
            ingest.partition_path(data_dir, "board_runs", d),
        )
    rates = []
    for k in range(30):
        day = date(2026, 10, 10) + timedelta(days=k)
        for cur, per_eur in (("EUR", 1.0), ("USD", 1.10), ("GBP", 0.84), ("CAD", 1.52)):
            rates.append({"rate_date": day, "currency": cur, "per_eur": per_eur,
                          "usd_per_unit": 1.10 / per_eur, "source": "synthetic"})  # fmt: skip
    fx.write(rates, data_dir)
    seeds_dir.mkdir(parents=True, exist_ok=True)
    (seeds_dir / "boards.csv").write_text(
        "provider,board,company,company_name_source,jobs_at_recon,us_jobs_at_recon,us_share,"
        "tech_share,sources,recon_date\n"
        + "".join(f"{p},{b},{c},synthetic,1,1,1,1,synthetic,2026-10-25\n" for p, b, c in BOARDS)
    )
    return dates
