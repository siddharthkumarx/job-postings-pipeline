"""Pick the tracked boards from verify results and write seeds/boards.csv + docs/sources.md.

Selection rules (also in docs/decisions.md, D-004):

1. the API answered 200 with at least ``min_jobs`` listed jobs;
2. mostly US: of the jobs whose country could be determined, at least
   ``min_us_share`` are open in the US, and the country is known for at least
   ``min_known_share`` of the jobs;
3. tech: at least ``min_tech_share`` of the titles match the tech-title signal;
4. one board per company: boards are grouped by normalised company name and
   the board with the most jobs wins (companies migrating between ATSs often
   keep an old board alive);
5. if more boards pass than ``target``, keep the ``target`` with the most US
   tech jobs.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from jobpipe.csvio import read_csv, write_csv

BOARD_FIELDS = [
    "provider", "board", "company", "company_name_source", "jobs_at_recon", "us_jobs_at_recon",
    "us_share", "tech_share", "sources", "recon_date",
]  # fmt: skip

_SUFFIX = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|co|company|technologies|technology|labs|hq|careers|jobs)\b\.?",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class Thresholds:
    min_jobs: int = 1
    min_us_share: float = 0.5
    min_known_share: float = 0.5
    min_tech_share: float = 0.2
    target: int = 1500


def norm_company(name: str) -> str:
    return _NON_ALNUM.sub("", _SUFFIX.sub("", name.lower()))


def pretty_token(token: str) -> str:
    words = re.split(r"[-_ .]+", token)
    return " ".join(w[:1].upper() + w[1:] for w in words if w)


def company_name(row: dict[str, str]) -> tuple[str, str]:
    if row.get("company_name"):
        return row["company_name"], "api"
    if row.get("yc_name") and "yc" in row.get("sources", "").split("|"):
        return row["yc_name"], "yc"
    return pretty_token(row["token"]), "board name"


def _f(row: dict[str, str], key: str) -> int:
    try:
        return int(row.get(key) or 0)
    except ValueError:
        return 0


def metrics(row: dict[str, str]) -> dict[str, float]:
    jobs = _f(row, "jobs")
    us, non_us = _f(row, "us_jobs"), _f(row, "non_us_jobs")
    known = us + non_us
    return {
        "jobs": jobs,
        "us": us,
        "us_share": us / known if known else 0.0,
        "known_share": known / jobs if jobs else 0.0,
        "tech_share": _f(row, "tech_jobs") / jobs if jobs else 0.0,
        "us_tech": _f(row, "us_tech_jobs"),
    }


def funnel_and_select(
    rows: list[dict[str, str]], th: Thresholds
) -> tuple[list[dict[str, Any]], dict[str, Counter[str]]]:
    stages = ["verified", "http_200", "has_jobs", "mostly_us", "tech", "deduped", "kept"]
    funnel: dict[str, Counter[str]] = {s: Counter() for s in stages}
    passing: list[tuple[dict[str, str], dict[str, float]]] = []
    for row in rows:
        p = row["provider"]
        funnel["verified"][p] += 1
        if row["outcome"] != "ok":
            continue
        funnel["http_200"][p] += 1
        m = metrics(row)
        if m["jobs"] < th.min_jobs:
            continue
        funnel["has_jobs"][p] += 1
        if m["us_share"] < th.min_us_share or m["known_share"] < th.min_known_share:
            continue
        funnel["mostly_us"][p] += 1
        if m["tech_share"] < th.min_tech_share:
            continue
        funnel["tech"][p] += 1
        passing.append((row, m))

    best: dict[str, tuple[dict[str, str], dict[str, float]]] = {}
    for row, m in passing:
        key = norm_company(company_name(row)[0]) or row["token"].lower()
        cur = best.get(key)
        if cur is None or m["jobs"] > cur[1]["jobs"]:
            best[key] = (row, m)
    deduped = list(best.values())
    for row, _ in deduped:
        funnel["deduped"][row["provider"]] += 1
    deduped.sort(key=lambda rm: (-rm[1]["us_tech"], -rm[1]["jobs"], rm[0]["token"].lower()))
    kept = deduped[: th.target]

    out: list[dict[str, Any]] = []
    today = date.today().isoformat()
    for row, m in kept:
        name, src = company_name(row)
        funnel["kept"][row["provider"]] += 1
        out.append(
            {
                "provider": row["provider"],
                "board": row["token"],
                "company": name,
                "company_name_source": src,
                "jobs_at_recon": int(m["jobs"]),
                "us_jobs_at_recon": int(m["us"]),
                "us_share": round(m["us_share"], 3),
                "tech_share": round(m["tech_share"], 3),
                "sources": row["sources"],
                "recon_date": today,
            }
        )
    out.sort(key=lambda r: (r["provider"], str(r["company"]).lower()))
    return out, funnel


def _source_label(sources: str) -> str:
    parts = sources.split("|")
    labels = []
    if any(s.startswith("cc:") for s in parts):
        labels.append("Common Crawl")
    if "yc" in parts:
        labels.append("YC directory")
    return " + ".join(labels)


def render_sources_md(
    boards: list[dict[str, Any]],
    funnel: dict[str, Counter[str]],
    th: Thresholds,
    harvest_summary: dict[str, Any],
    check_ids: list[str],
) -> str:
    providers = ["greenhouse", "lever", "ashby"]
    lines = [
        "# Sources",
        "",
        "The tracked companies and the job board each one is read from. Generated by",
        "`jobpipe recon-select` from live checks "
        + ", ".join(f"`checks/results/{c}/`" for c in check_ids)
        + ".",
        "",
        "## Seed sources",
        "",
        "| Source | What it gave | Link |",
        "|---|---|---|",
        "| Common Crawl URL index, crawls "
        + ", ".join(f"`{c}`" for c in harvest_summary.get("crawls", []))
        + " | board names from captured URLs on boards.greenhouse.io, job-boards.greenhouse.io,"
        " jobs.lever.co and jobs.ashbyhq.com | https://index.commoncrawl.org/ |",
        "| Y Combinator company directory (yc-oss JSON mirror) | guessed board names for"
        " active, hiring US companies, confirmed or rejected through the APIs |"
        " https://www.ycombinator.com/companies ,"
        " https://yc-oss.github.io/api/companies/all.json |",
        "",
        "## Selection rules",
        "",
        f"- API answered 200 with at least {th.min_jobs} listed job(s).",
        f"- Mostly US: at least {th.min_us_share:.0%} of jobs with a known country are in the US,"
        f" and the country is known for at least {th.min_known_share:.0%} of jobs.",
        f"- Tech: at least {th.min_tech_share:.0%} of titles match the tech-title signal"
        " (`src/jobpipe/recon/signals.py`).",
        "- One board per company (largest board wins); then the"
        f" {th.target:,} boards with the most US tech jobs.",
        "",
        "## Funnel",
        "",
        "| Stage | " + " | ".join(providers) + " | Total |",
        "|---|" + "---:|" * (len(providers) + 1),
    ]
    for stage, counts in funnel.items():
        vals = [counts.get(p, 0) for p in providers]
        lines.append(f"| {stage} | " + " | ".join(f"{v:,}" for v in vals) + f" | {sum(vals):,} |")
    totals = Counter(b["provider"] for b in boards)
    jobs: Counter[str] = Counter()
    for b in boards:
        jobs[b["provider"]] += int(b["jobs_at_recon"])
    lines += [
        "",
        "## Totals per provider",
        "",
        "| Provider | Boards | Open jobs at recon |",
        "|---|---:|---:|",
    ]
    for p in providers:
        lines.append(f"| {p} | {totals.get(p, 0):,} | {jobs.get(p, 0):,} |")
    lines.append(f"| **total** | **{sum(totals.values()):,}** | **{sum(jobs.values()):,}** |")
    lines += [
        "",
        "## Boards",
        "",
        "US share = share of jobs with a known country that are open in the US."
        " Company names come from the Greenhouse API, the YC directory, or the board name"
        " (Lever and Ashby APIs do not return a company name).",
        "",
        "| Provider | Board name | Company | Open jobs (recon) | US share | Notes |",
        "|---|---|---|---:|---:|---|",
    ]
    for b in boards:
        notes = [_source_label(str(b["sources"])), f"tech {float(b['tech_share']):.0%}"]
        if b["company_name_source"] != "api":
            notes.append(f"name from {b['company_name_source']}")
        company = str(b["company"]).replace("|", "/")
        lines.append(
            f"| {b['provider']} | `{b['board']}` | {company} | {b['jobs_at_recon']:,} |"
            f" {float(b['us_share']):.0%} | {'; '.join(notes)} |"
        )
    return "\n".join(lines) + "\n"


def run(
    verify_csv: Path,
    harvest_summary: dict[str, Any],
    check_ids: list[str],
    out_csv: Path,
    out_md: Path,
    th: Thresholds,
) -> dict[str, Any]:
    rows = read_csv(verify_csv)
    boards, funnel = funnel_and_select(rows, th)
    write_csv(out_csv, boards, BOARD_FIELDS)
    out_md.write_text(render_sources_md(boards, funnel, th, harvest_summary, check_ids))
    return {
        "funnel": {k: dict(v) for k, v in funnel.items()},
        "kept": len(boards),
    }
