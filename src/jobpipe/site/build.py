"""Build the static dashboard (site/index.html + assets) from the warehouse.

Every number on the page is queried from the DuckDB warehouse or read from
public/status.json, both produced by real runs.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

from jobpipe.site import charts as c

ASSETS = Path(__file__).parent / "assets"
DATA_ROLES = ["data_engineer", "analytics_engineer", "data_analyst", "ml_engineer"]
LABELS = {
    "software_engineer": "Software engineer",
    "data_engineer": "Data engineer",
    "analytics_engineer": "Analytics engineer",
    "data_analyst": "Data analyst",
    "data_scientist": "Data scientist",
    "ml_engineer": "ML engineer",
    "devops_sre": "DevOps / SRE",
    "security": "Security",
    "product_manager": "Product manager",
    "design": "Design",
    "qa_test": "QA / test",
    "it_support": "IT support",
    "hardware_engineer": "Hardware engineer",
    "solutions_engineer": "Solutions engineer",
    "engineering_manager": "Engineering manager",
    "sales": "Sales",
    "marketing": "Marketing",
    "customer_success": "Customer success",
    "operations": "Operations",
    "finance": "Finance",
    "people_hr": "People / HR",
    "legal": "Legal",
    "other": "Other",
    "all": "All roles",
    "intern": "Intern",
    "junior": "Junior",
    "mid": "Mid",
    "senior": "Senior",
    "staff_principal": "Staff / principal",
    "manager": "Manager",
    "director": "Director",
    "vp_exec": "VP / exec",
    "remote": "Remote",
    "hybrid": "Hybrid",
    "onsite": "On-site",
    "unknown": "Unknown",
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
}


def label(key: str | None) -> str:
    return LABELS.get(key or "", key or "–")


def q(con: Any, sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = con.execute(sql, params or []).fetchall()
    return rows


def gather(duckdb_path: Path) -> dict[str, Any]:
    import duckdb

    con = duckdb.connect(str(duckdb_path))
    try:
        latest = q(con, "select max(run_date) from history.int_run_calendar")[0][0]
        d: dict[str, Any] = {"latest": latest}
        d["kpi"] = q(
            con,
            """select
                (select count(*) from gold.dim_company where last_fetch_status = 'ok'),
                count(*) filter (where is_open),
                avg(case when country_code = 'US' then 1.0 else 0 end) filter (where is_open),
                count(*) filter (where is_open and role_family in ('data_engineer',
                    'analytics_engineer','data_analyst','ml_engineer')),
                avg(case when salary_min_usd_annual is not null then 1.0 else 0 end)
                    filter (where is_open and country_code = 'US'),
                avg(case when remote_type = 'remote' then 1.0 else 0 end) filter (where is_open)
            from gold.fct_job_postings""",
        )[0]
        d["daily"] = q(
            con,
            """select run_date, count(*) from history.int_postings_daily
               group by 1 order by 1""",
        )
        d["flows"] = q(
            con,
            """select c.run_date,
                 (select count(*) from gold.fct_job_postings f
                   where f.first_seen = c.run_date and not f.left_censored),
                 (select count(*) from gold.fct_job_postings f where f.closed_on = c.run_date)
               from history.int_run_calendar c order by 1""",
        )
        d["families"] = q(
            con,
            """select role_family, count(*) from gold.fct_job_postings where is_open
               group by 1 order by 2 desc""",
        )
        d["providers"] = q(
            con,
            """select provider, count(*), sum(open_postings) from gold.dim_company
               where last_fetch_status = 'ok' group by 1 order by 1""",
        )
        d["data_by_family"] = q(
            con,
            """select role_family, count(*),
                 median((salary_min_usd_annual + salary_max_usd_annual) / 2)
                     filter (where country_code = 'US'),
                 avg(case when remote_type = 'remote' then 1.0 else 0 end)
               from gold.mart_data_roles where is_open group by 1""",
        )
        d["data_daily"] = q(
            con,
            """select run_date, role_family, count(*) from history.int_postings_daily
               where role_family in ('data_engineer','analytics_engineer','data_analyst',
                   'ml_engineer') group by 1, 2 order by 1, 2""",
        )
        d["data_seniority"] = q(
            con,
            """select seniority, count(*) from gold.mart_data_roles where is_open
               group by 1 order by 2 desc""",
        )
        d["data_states"] = q(
            con,
            """select state_code, count(*) from gold.mart_data_roles
               where is_open and country_code = 'US' and state_code is not null
               group by 1 order by 2 desc limit 10""",
        )
        d["salary"] = q(
            con,
            """select role_family, p25_usd, median_usd, p75_usd, postings_with_salary
               from gold.mart_salary_bands
               where seniority = 'all' and role_family <> 'all' and postings_with_salary >= 20
               order by median_usd desc""",
        )
        d["salary_seniority"] = q(
            con,
            """select seniority, p25_usd, median_usd, p75_usd, postings_with_salary
               from gold.mart_salary_bands
               where role_family = 'all' and seniority <> 'all' and postings_with_salary >= 20
               order by median_usd""",
        )
        d["days_bands"] = q(
            con,
            """select band, closed_postings, share, median_days_open
               from gold.mart_days_open_bands where role_family = 'all' order by band_order""",
        )
        d["age_bands"] = q(
            con,
            """with o as (
                 select datediff('day', cast(published_at as date), ?) as age
                 from gold.fct_job_postings where is_open and published_at is not null)
               select band, n from (
                 select case when age <= 7 then '0-7' when age <= 14 then '8-14'
                   when age <= 30 then '15-30' when age <= 60 then '31-60'
                   when age <= 90 then '61-90' else '91+' end as band, count(*) as n,
                   min(age) as k
                 from o where age >= 0 group by 1) order by k""",
            [latest],
        )
        d["age_median"] = q(
            con,
            """select median(datediff('day', cast(published_at as date), ?))
               from gold.fct_job_postings where is_open and published_at is not null
               and cast(published_at as date) <= ?""",
            [latest, latest],
        )[0][0]
        d["companies"] = q(
            con,
            """select company_name, provider, open_postings, open_us_postings
               from gold.dim_company where last_fetch_status = 'ok'
               order by open_postings desc, company_name limit 25""",
        )
    finally:
        con.close()
    return d


def _kpi(label_: str, value: str, sub: str = "") -> str:
    sub_html = f'<span class="sub">{escape(sub)}</span>' if sub else ""
    return (
        f'<li class="kpi"><span class="label">{escape(label_)}</span>'
        f'<span class="value">{escape(value)}</span>{sub_html}</li>'
    )


def render(d: dict[str, Any], st: dict[str, Any]) -> str:
    latest: date | None = d["latest"]
    companies, open_roles, us_share, data_open, salary_share, remote_share = d["kpi"]
    days = [(str(r[0]), float(r[1])) for r in d["daily"]]
    flows_new = [(str(r[0]), float(r[1])) for r in d["flows"]]
    flows_closed = [(str(r[0]), float(r[2])) for r in d["flows"]]

    kpis = "".join(
        [
            _kpi("Companies tracked", c.fmt_int(companies), "boards fetched OK"),
            _kpi("Open roles", c.fmt_int(open_roles), f"latest run {latest}"),
            _kpi("Open roles in the US", c.fmt_pct(us_share), "share of open roles"),
            _kpi("Open data roles", c.fmt_int(data_open), "DE · AE · DA · MLE"),
            _kpi("US roles with salary", c.fmt_pct(salary_share), "pay published"),
            _kpi(
                "Days running",
                c.fmt_int(st.get("days_running")),
                f"missed runs: {st.get('missed_runs', '–')}",
            ),
        ]
    )

    trends = (
        '<div class="grid">'
        f'<div class="panel">{c.line([("Open roles", days, "teal")], caption="Open roles per run")}'
        + c.table(
            ["Run date", "Open roles"],
            [(x, c.fmt_int(y)) for x, y in days],
            caption="Table: open roles per run",
            numeric={1},
        )
        + "</div>"
        '<div class="panel">'
        + c.line(
            [("New roles", flows_new, "teal"), ("Closed roles", flows_closed, "amber")],
            caption="New vs closed roles per run",
        )
        + c.table(
            ["Run date", "New", "Closed"],
            [(str(r[0]), c.fmt_int(r[1]), c.fmt_int(r[2])) for r in d["flows"]],
            caption="Table: new and closed roles per run",
            numeric={1, 2},
        )
        + '<p class="section-note">A role counts as closed after it is missing from two runs in a'
        " row in which its board was fetched successfully. Roles already open on a board's first"
        " run are not counted as new.</p></div></div>"
    )

    fam_rows = [(label(f), float(n), c.fmt_int(n)) for f, n in d["families"]]
    families = (
        '<div class="grid"><div class="panel">'
        + c.hbars(
            fam_rows, caption="Open roles by role family", highlight={label(f) for f in DATA_ROLES}
        )
        + '<p class="section-note">Amber bars are the four data roles.</p></div>'
        '<div class="panel">'
        + c.hbars(
            [(label(p), float(o or 0), f"{c.fmt_int(o)} · {n} cos") for p, n, o in d["providers"]],
            caption="Open roles by job-board provider",
        )
        + "</div></div>"
    )

    by_fam = {r[0]: r for r in d["data_by_family"]}
    data_rows = [
        (
            label(f),
            float(by_fam[f][1]) if f in by_fam else 0.0,
            c.fmt_int(by_fam[f][1]) if f in by_fam else "0",
        )
        for f in DATA_ROLES
    ]
    series_tones = {
        "data_engineer": "teal",
        "analytics_engineer": "teal",
        "data_analyst": "teal",
        "ml_engineer": "teal",
    }
    data_daily: dict[str, list[tuple[str, float]]] = {}
    for run_date, fam, n in d["data_daily"]:
        data_daily.setdefault(fam, []).append((str(run_date), float(n)))
    multiples = "".join(
        '<div class="panel">'
        + c.line(
            [(label(f), data_daily.get(f, []), series_tones[f])],
            caption=f"{label(f)}: open roles per run",
            height=140,
        )
        + "</div>"
        for f in DATA_ROLES
    )
    data_section = (
        '<div class="grid"><div class="panel">'
        + c.hbars(data_rows, caption="Open data roles today")
        + c.table(
            ["Role", "Open", "Median US salary", "Remote share"],
            [
                (
                    label(f),
                    c.fmt_int(by_fam[f][1]),
                    c.fmt_usd(by_fam[f][2]),
                    c.fmt_pct(by_fam[f][3]),
                )
                for f in DATA_ROLES
                if f in by_fam
            ],
            caption="Table: data roles",
            numeric={1, 2, 3},
        )
        + "</div>"
        '<div class="panel">'
        + c.hbars(
            [(label(s), float(n), c.fmt_int(n)) for s, n in d["data_seniority"]],
            caption="Open data roles by seniority",
        )
        + "</div>"
        '<div class="panel">'
        + c.hbars(
            [(s, float(n), c.fmt_int(n)) for s, n in d["data_states"]],
            caption="Open US data roles: top states",
        )
        + "</div></div>"
        f'<div class="grid">{multiples}</div>'
    )

    sal = d["salary"]
    sal_sen = d["salary_seniority"]
    allv = [v for r in sal + sal_sen for v in (r[1], r[3]) if v is not None]
    lo = (min(allv) // 20000) * 20000 if allv else 0
    hi = (max(allv) // 20000 + 1) * 20000 if allv else 1
    salary_section = (
        '<div class="grid"><div class="panel">'
        + c.ranges(
            [(label(r[0]), r[1], r[2], r[3], int(r[4])) for r in sal],
            caption="Annual USD salary, US roles: 25th-75th percentile, median marked",
            lo=lo,
            hi=hi,
        )
        + c.table(
            ["Role", "p25", "Median", "p75", "Roles with salary"],
            [
                (label(r[0]), c.fmt_usd(r[1]), c.fmt_usd(r[2]), c.fmt_usd(r[3]), c.fmt_int(r[4]))
                for r in sal
            ],
            caption="Table: salary bands by role",
            numeric={1, 2, 3, 4},
        )
        + '</div><div class="panel">'
        + c.ranges(
            [(label(r[0]), r[1], r[2], r[3], int(r[4])) for r in sal_sen],
            caption="Annual USD salary by seniority (all roles)",
            lo=lo,
            hi=hi,
        )
        + '<p class="section-note">Midpoint of each published range, annualised (hourly × 2,080)'
        " and converted at the ECB reference rate on the day the role was first seen. Groups"
        " with fewer than 20 salaries are hidden.</p></div></div>"
    )

    bands = d["days_bands"]
    closed_total = sum(int(b[1]) for b in bands)
    if closed_total:
        med = bands[0][3]
        days_open = c.columns(
            [(b[0], float(b[1]), c.fmt_pct(b[2])) for b in bands],
            caption=f"Days open for closed roles (median {c.fmt_int(med)} days, n={closed_total:,})",
        )
    else:
        days_open = (
            '<p class="empty">No closed roles with a known opening date yet: roles already'
            " open on the first run are excluded, so this fills in as runs accumulate.</p>"
        )
    age = c.columns(
        [(b, float(n), c.fmt_int(n)) for b, n in d["age_bands"]],
        caption=f"Age of open roles by provider publish date (median {c.fmt_int(d['age_median'])} days)",
    )
    days_section = (
        f'<div class="grid"><div class="panel">{days_open}</div>'
        f'<div class="panel">{age}<p class="section-note">Days since the provider\'s'
        " published/created timestamp (Greenhouse first published, Lever created, Ashby"
        " published).</p></div></div>"
    )

    company_table = (
        '<div class="data-table"><div class="table-wrap"><table><caption class="quiet"'
        ' style="text-align:left;padding:6px 8px">Top 25 companies by open roles</caption>'
        '<thead><tr><th scope="col">Company</th><th scope="col">Board</th>'
        '<th scope="col" class="num">Open roles</th><th scope="col" class="num">US roles</th>'
        "</tr></thead><tbody>"
        + "".join(
            f"<tr><td>{escape(n)}</td><td>{escape(label(p))}</td>"
            f'<td class="num">{c.fmt_int(o)}</td><td class="num">{c.fmt_int(u)}</td></tr>'
            for n, p, o, u in d["companies"]
        )
        + "</tbody></table></div></div>"
    )

    nav = "".join(
        f'<li><a href="#{a}">{t}</a></li>'
        for a, t in [
            ("overview", "Overview"),
            ("trends", "Hiring trends"),
            ("families", "Role families"),
            ("data-roles", "Data roles"),
            ("salary", "Salary bands"),
            ("days-open", "Days open"),
            ("companies", "Companies"),
            ("about", "About the data"),
        ]
    )
    meta = (
        f"<span>Latest run {latest}</span><span>First run {st.get('first_run', '–')}</span>"
        f"<span>Status {escape(str(st.get('last_status', '–')))}</span>"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>US tech hiring: daily job-board data</title>
<meta name="description" content="Daily open roles at {c.fmt_int(companies)} US tech companies from their public Greenhouse, Lever and Ashby job boards: hiring trends, data roles, salary bands and days open.">
<meta name="theme-color" content="#0B1416">
<link rel="preload" href="assets/fonts/instrument-sans-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="assets/fonts/ibm-plex-mono-latin-500-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="assets/site.css">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' rx='3' fill='%230B1416'/%3E%3Crect x='3' y='8' width='2' height='5' fill='%232FBFAE'/%3E%3Crect x='7' y='5' width='2' height='8' fill='%232FBFAE'/%3E%3Crect x='11' y='3' width='2' height='10' fill='%23E9A93C'/%3E%3C/svg%3E">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="top"><div class="wrap">
<h1>US tech hiring, from the job boards</h1>
<p class="lede">Open roles at {c.fmt_int(companies)} US tech companies, read once a day from their public Greenhouse, Lever and Ashby job boards and modelled in DuckDB + dbt.</p>
<p class="meta">{meta}</p>
</div></header>
<nav class="sections" aria-label="Sections"><div class="wrap"><ul>{nav}</ul></div></nav>
<main id="main" class="wrap">
<section id="overview" aria-labelledby="h-overview"><h2 id="h-overview" class="skip">Overview</h2><ul class="kpis" role="list">{kpis}</ul>
<p class="section-note" style="margin-top:12px">Remote share of open roles: {c.fmt_pct(remote_share)}.</p></section>
<section id="trends" aria-labelledby="h-trends"><h2 id="h-trends">Hiring trends</h2><p class="section-note">Every point is one daily run.</p>{trends}</section>
<section id="families" aria-labelledby="h-families"><h2 id="h-families">Role families</h2><p class="section-note">Titles are mapped to role families by a versioned rule table (taxonomy {escape(str(d.get("taxonomy", "2026-11-03")))}).</p>{families}</section>
<section id="data-roles" aria-labelledby="h-data"><h2 id="h-data">Data roles</h2><p class="section-note">Data engineers, analytics engineers, data analysts and ML engineers.</p>{data_section}</section>
<section id="salary" aria-labelledby="h-salary"><h2 id="h-salary">Salary bands</h2>{salary_section}</section>
<section id="days-open" aria-labelledby="h-days"><h2 id="h-days">Days open</h2>{days_section}</section>
<section id="companies" aria-labelledby="h-companies"><h2 id="h-companies">Companies</h2>{company_table}</section>
<section id="about" aria-labelledby="h-about"><h2 id="h-about">About the data</h2>
<div class="panel"><p>Source: the official public job-board APIs of Greenhouse, Lever and Ashby, one request per board per day with per-host rate limits. Only metadata and derived fields are kept: title, company, department, location, remote type, salary range, dates and the job URL. Job-description text and personal data are never stored. Descriptions are read in memory only, to extract salary and remote hints.</p>
<p>Downloads: the monthly Parquet dataset is attached to the repository's releases; summary CSVs and the run log live in <code>public/</code>. Model documentation: <a href="dbt-docs/index.html">dbt docs</a>.</p></div></section>
</main>
<footer><div class="wrap"><p>Built by Siddharth Kumar, web scraping and data engineering (<a href="https://siddharthkumar.com">siddharthkumar.com</a>). Numbers come from daily pipeline runs; see the run log for misses and holds.</p></div></footer>
</body>
</html>
"""


def build(duckdb_path: Path, public_dir: Path, out_dir: Path) -> Path:
    data = gather(duckdb_path)
    status_path = public_dir / "status.json"
    st = json.loads(status_path.read_text()) if status_path.exists() else {}
    out_dir.mkdir(parents=True, exist_ok=True)
    assets = out_dir / "assets"
    if assets.exists():
        shutil.rmtree(assets)
    shutil.copytree(ASSETS, assets)
    index = out_dir / "index.html"
    index.write_text(render(data, st), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("")
    return index
