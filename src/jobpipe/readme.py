"""Render README.md (and the dataset card) from templates and real run outputs.

Called by every daily run after publishing (``jobpipe readme``), so numbers that grow
(days running, rows, runs) are never hard-coded: they come from ``public/`` files or
from shields.io badges that read ``public/badges/*.json``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import jinja2
import yaml

from jobpipe.readme_data import ReadmeData, load

ROOT_TEMPLATES = Path("templates")
FORBIDDEN = ("{{", "{%", "<!--", "TODO", "TBD", "lorem", "placeholder", "XXX")

WORKTYPE = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "On-site", "unknown": "Not stated"}


def _num(v: Any) -> str:
    try:
        return f"{int(float(v)):,}"
    except (TypeError, ValueError):
        return "0"


def _short(s: str, n: int) -> str:
    s = " ".join(str(s).split()).replace("|", "/")
    return s if len(s) <= n else s[: n - 1].rstrip(" ,-–") + "…"


def _salary(row: dict[str, str]) -> str:
    lo, hi = row.get("salary_min_usd_annual"), row.get("salary_max_usd_annual")
    if not lo:
        return "Not published"
    lo_f, hi_f = float(lo), float(hi or lo)
    return f"${lo_f:,.0f} to ${hi_f:,.0f}" if hi_f != lo_f else f"${lo_f:,.0f}"


def _example(name: str, value: Any) -> str:
    if value is None or value == "":
        return {
            "closed_on": "empty while the job is open",
        }.get(name, "empty")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.0f}" if value.is_integer() else f"{value}"
    text = str(value).replace("|", "/")
    if name == "job_url":
        return f"[link]({text})"
    if name in ("posting_key", "company_id"):
        return f"`{text[:12]}…`"
    return _short(text, 48)


PLAIN_TYPES = {
    "varchar": "text", "double": "number", "integer": "whole number", "boolean": "yes / no",
    "date": "date", "timestamp with time zone": "date and time (UTC)",
}  # fmt: skip
PLAIN_MEANINGS = {
    "posting_key": "Unique ID of the job posting in this dataset",
    "provider": "Job-board software the company uses: Greenhouse, Lever or Ashby",
    "board": "The company's board name on that job board",
    "company_id": "Unique ID of the company in this dataset",
    "company_name": "Company name",
    "posting_id": "The job board's own ID for the posting",
    "title": "Job title as the company wrote it",
    "role_family": "Role type worked out from the title (e.g. data engineer)",
    "seniority": "Level worked out from the title (intern to VP)",
    "seniority_source": "Where the level came from: the title, the job ad text, or a default",
    "department": "Department or team as published",
    "location_raw": "Main location as the company wrote it",
    "country_code": "Country code (US, GB …); empty if unknown",
    "state_code": "US state code, for US jobs",
    "city": "City, when it can be read from the location",
    "remote_type": "Remote, hybrid, on-site, or not stated",
    "employment_type": "Full-time, part-time, contract, internship, temporary, or not stated",
    "salary_min": "Lowest salary as published, in its own currency and period",
    "salary_max": "Highest salary as published",
    "salary_currency": "Currency of the published salary",
    "salary_period": "Whether the published salary is per year, month, week, day or hour",
    "salary_min_annual": "Lowest salary converted to a yearly amount",
    "salary_max_annual": "Highest salary converted to a yearly amount",
    "salary_min_usd_annual": "Lowest yearly salary in US dollars",
    "salary_max_usd_annual": "Highest yearly salary in US dollars",
    "salary_source": "Where the salary came from: the job board's salary field or the ad text",
    "fx_rate_date": "Date of the official exchange rate used for the dollar conversion",
    "job_url": "Link to the original posting",
    "published_at": "When the company published or last updated the posting",
    "first_seen": "First day the job was seen",
    "last_seen": "Last day the job was seen",
    "closed_on": "Day the job was counted as closed (missing two days in a row)",
    "is_open": "Whether the job was open in the latest run",
    "days_open": "Days the job has been open so far, or was open in total",
    "left_censored": "Yes if the job was already open on the first day it was tracked",
    "version_count": "How many times the title, location or salary changed, plus one",
    "taxonomy_version": "Version of the rules used for role type and level",
}


def dictionary(example: dict[str, Any]) -> list[dict[str, str]]:
    from jobpipe.contracts import parse

    cols = parse().get("fct_job_postings", [])
    return [
        {
            "name": name,
            "type": PLAIN_TYPES.get(dtype, dtype),
            "meaning": PLAIN_MEANINGS.get(name, meaning.replace("|", "/")),
            "example": _example(name, example.get(name)),
        }
        for name, dtype, meaning in cols
    ]


def context(d: ReadmeData, cfg: dict[str, Any]) -> dict[str, Any]:
    ch = {r["kind"]: r for r in d.changes}
    first_day = "first_day" in ch or not d.changes
    run = d.last_run
    ing = run.get("ingest") or {}
    spot = ing.get("spot_check") or {}
    dbt = run.get("dbt") or {}
    raw = f"https://raw.githubusercontent.com/{cfg['public_repo']}/{cfg['branch']}/public/badges"

    def badge(name: str) -> str:
        return "https://img.shields.io/endpoint?style=flat-square&url=" + quote(
            f"{raw}/{name}.json", safe=""
        )

    sample_names = ", ".join(r["company_name"] for r in d.sample[:3])
    return {
        "cfg": cfg,
        "badge": badge,
        "companies": d.companies,
        "open_jobs": d.open_jobs,
        "run_date": d.run_date,
        "minutes": d.minutes,
        "sample": d.sample,
        "first_day": first_day,
        "prev_date": ch.get("new_total", {}).get("detail", ""),
        "new_total": ch.get("new_total", {}).get("count", 0),
        "closed_total": ch.get("closed_total", {}).get("count", 0),
        "salary_changed": ch.get("salary_changed", {}).get("count", 0),
        "title_changed": ch.get("title_changed", {}).get("count", 0),
        "most_new": [
            f"{r['company']} ({r['count']})" for r in d.changes if r["kind"] == "most_new"
        ],
        "most_closed": [
            f"{r['company']} ({r['count']})" for r in d.changes if r["kind"] == "most_closed"
        ],
        "spot": spot,
        "q": d.quality,
        "invalid": ing.get("invalid_postings", 0),
        "boards_ok": ing.get("boards_ok", run.get("boards_ok", 0)),
        "boards": ing.get("boards", run.get("boards", d.companies)),
        "requests": ing.get("requests") or ing.get("boards", 0),
        "tests": dbt.get("pass", 0),
        "dbt_tests": dbt.get("pass", 0),
        "by_provider": d.boards_by_provider,
        "incidents": d.incidents,
        "dictionary": dictionary(d.example),
        "hero_alt": (
            f"Animation: open tech jobs are spread across {d.companies:,} company job boards; "
            f"one daily run collects them into one table (real rows: {sample_names}); result: "
            f"{d.open_jobs:,} open jobs at {d.companies:,} US tech companies, checked every day"
        ),
        "pipeline_alt": (
            "Animation of the pipeline: source (3 job boards), collect (Python), check (dbt "
            f"and pytest), store (DuckDB), deliver (GitHub, Hugging Face); {d.companies:,} job "
            f"boards in about {d.minutes:.0f} minutes every morning"
        ),
        "data_roles_alt": "Bar chart of open data roles today: "
        + ", ".join(
            f"{r['role_family'].replace('_', ' ')} {int(r['open_roles']):,}" for r in d.data_roles
        ),
        "dashboard_alt": (
            f"Screenshot of the live dashboard: {d.companies:,} companies tracked and open roles "
            "by role family, data roles, salary bands and days open"
        ),
        "maintenance_alt": (
            "Animation: one square per daily run, amber for a held or failed run; a real "
            "incident, its fix the same day, and every job board read in the latest run"
        ),
        "lineage_alt": (
            "dbt lineage graph: raw inputs feed cleaned staging models, then history models, "
            "then the published marts"
        ),
    }


def environment() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT_TEMPLATES)),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,  # noqa: S701 - renders Markdown, not HTML
    )
    env.filters["num"] = _num
    env.filters["short"] = _short
    env.filters["salary"] = _salary
    env.filters["worktype"] = lambda v: WORKTYPE.get(v, v)
    return env


def check_rendered(text: str) -> list[str]:
    problems = [f"contains {f!r}" for f in FORBIDDEN if f.lower() in text.lower()]
    if re.search(r"\]\(\s*\)", text):
        problems.append("empty link target")
    return problems


def render(root: Path = Path("."), out: Path = Path("README.md")) -> str:
    cfg = yaml.safe_load((ROOT_TEMPLATES / "readme.yml").read_text())
    d = load(root)
    env = environment()
    ctx = context(d, cfg)
    text = env.get_template("README.md.j2").render(**ctx)
    text = re.sub(r"\n{3,}", "\n\n", text)
    problems = check_rendered(text)
    if problems:
        raise RuntimeError(f"README did not render cleanly: {problems}")
    out.write_text(text, encoding="utf-8")
    card = env.get_template("dataset-card.md.j2").render(**ctx)
    card = re.sub(r"\n{3,}", "\n\n", card)
    Path("docs/dataset-card.md").write_text(card, encoding="utf-8")
    return text


def main() -> int:
    from jobpipe.visuals.build import build_all

    sizes = build_all(Path("assets"))
    render()
    print({"visuals": sizes, "readme": "README.md"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
