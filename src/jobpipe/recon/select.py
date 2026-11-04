"""Pick the tracked boards from verify results and write seeds/boards.csv + docs/sources.md.

Selection rules (approved by the owner; docs/decisions.md D-014):

1. the API answered 200 with at least 1 listed job;
2. at least 1 US job;
3. mostly US: of the jobs whose country could be determined, at least
   ``min_us_share`` are in the US, and the country is known for at least
   ``min_known_share`` of the jobs;
4. tech: at least ``min_tech_share`` of the titles match the tech-title signal;
5. companies only: staffing/recruiting agencies, job aggregators and test/demo
   boards are dropped (name/board-name rules here plus the reviewed list in
   ``seeds/exclusions.csv``);
6. one board per company (normalised company name): the board with more open
   jobs wins and the other is recorded as a duplicate;
7. if more boards pass than ``target``, keep the ``target`` with the most US tech jobs.

Every candidate that is not kept gets exactly one reason.
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
    "us_share", "tech_share", "sources", "notes", "recon_date",
]  # fmt: skip
DROPPED_FIELDS = ["provider", "board", "company", "jobs", "us_jobs", "reason", "sources"]
PROVIDERS = ["greenhouse", "lever", "ashby"]

_SUFFIX = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|co|company|technologies|technology|labs|hq|careers|jobs)\b\.?",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
# Staffing / recruiting firms place candidates at other companies.
AGENCY = re.compile(
    r"staffing|\brecruit(?:ing|ers|ment) (?:agency|firm|group|partners|solutions)|"
    r"\bheadhunt|\bplacement (?:agency|firm)|\bmanpower\b|workforce solutions|"
    r"employment agency|executive search|search (?:partners|firm)",
    re.IGNORECASE,
)
# Aggregators repost other companies' jobs (portfolio boards, job sites) or collect general
# applications rather than real openings (talent pools).
AGGREGATOR = re.compile(
    r"\bportfolio\b|talent ?(?:pool|network|community|collective|marketplace)|"
    r"remote ?jobs|job ?(?:network|aggregator)|\bjobs? at (?:our|portfolio)",
    re.IGNORECASE,
)
TEST_DEMO = re.compile(
    r"(?:^|[-_ .])(?:test|testing|demo|sandbox|example|staging|sample|dummy)(?:[-_ .]|\d|$)"
    r"|^demo|demo$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Thresholds:
    min_jobs: int = 1
    min_us_share: float = 0.5
    min_known_share: float = 0.5
    min_tech_share: float = 0.4
    target: int = 1500
    minimum: int = 1000


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
        return int(float(row.get(key) or 0))
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


def load_exclusions(path: Path) -> dict[tuple[str, str], str]:
    if not path.exists():
        return {}
    return {
        (r["provider"], r["board"].lower()): r["reason"]
        for r in read_csv(path)
        if r.get("provider") and r.get("board")
    }


def company_kind(row: dict[str, str], exclusions: dict[tuple[str, str], str]) -> str | None:
    """'agency', 'aggregator', 'test/demo' or a reviewed reason; None for a normal company."""
    manual = exclusions.get((row["provider"], row["token"].lower()))
    if manual:
        return manual
    name = company_name(row)[0]
    token = row["token"]
    if TEST_DEMO.search(token) or TEST_DEMO.search(name):
        return "test or demo board"
    if AGENCY.search(name) or AGENCY.search(token):
        return "staffing or recruiting agency"
    if AGGREGATOR.search(name) or AGGREGATOR.search(token):
        return "job aggregator"
    return None


def reason_for(row: dict[str, str], th: Thresholds) -> str | None:
    """Reason a verified candidate fails the API/US/tech rules (None = passes)."""
    outcome = row["outcome"]
    if outcome == "not_found":
        return "board not found (HTTP 404)"
    if outcome != "ok":
        return f"API error ({outcome} {row.get('status') or ''})".strip()
    m = metrics(row)
    if m["jobs"] < th.min_jobs:
        return "no open jobs"
    if m["us"] == 0:
        return "0 US roles"
    if m["known_share"] < th.min_known_share:
        return f"country unknown for most jobs ({m['known_share']:.0%} known)"
    if m["us_share"] < th.min_us_share:
        return f"mostly non-US ({m['us_share']:.0%} US)"
    if m["tech_share"] < th.min_tech_share:
        return f"not a tech company ({m['tech_share']:.0%} tech titles)"
    return None


def select(
    rows: list[dict[str, str]], th: Thresholds, exclusions: dict[tuple[str, str], str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Counter[str]]]:
    stages = ["verified", "http_200", "has_jobs", "has_us_roles", "mostly_us", "tech",
              "companies_only", "deduped", "kept"]  # fmt: skip
    funnel: dict[str, Counter[str]] = {s: Counter() for s in stages}
    dropped: list[dict[str, Any]] = []
    passing: list[tuple[dict[str, str], dict[str, float]]] = []

    def drop(row: dict[str, str], reason: str) -> None:
        dropped.append(
            {
                "provider": row["provider"],
                "board": row["token"],
                "company": company_name(row)[0] if row["outcome"] == "ok" else "",
                "jobs": _f(row, "jobs"),
                "us_jobs": _f(row, "us_jobs"),
                "reason": reason,
                "sources": row.get("sources", ""),
            }
        )

    for row in rows:
        p = row["provider"]
        funnel["verified"][p] += 1
        reason = reason_for(row, th)
        m = metrics(row)
        if row["outcome"] == "ok":
            funnel["http_200"][p] += 1
            if m["jobs"] >= th.min_jobs:
                funnel["has_jobs"][p] += 1
                if m["us"] > 0:
                    funnel["has_us_roles"][p] += 1
                    if reason is None or reason.startswith("not a tech"):
                        funnel["mostly_us"][p] += 1
        if reason is not None:
            drop(row, reason)
            continue
        funnel["tech"][p] += 1
        kind = company_kind(row, exclusions)
        if kind:
            drop(row, kind)
            continue
        funnel["companies_only"][p] += 1
        passing.append((row, m))

    groups: dict[str, list[tuple[dict[str, str], dict[str, float]]]] = {}
    for row, m in passing:
        key = norm_company(company_name(row)[0]) or row["token"].lower()
        groups.setdefault(key, []).append((row, m))
    deduped: list[tuple[dict[str, str], dict[str, float], str]] = []
    for members in groups.values():
        members.sort(key=lambda rm: (-rm[1]["jobs"], PROVIDERS.index(rm[0]["provider"])))
        best, best_m = members[0]
        notes = []
        for other, om in members[1:]:
            drop(
                other,
                f"duplicate: same company also on {best['provider']} `{best['token']}` "
                f"with more open jobs ({int(best_m['jobs'])} vs {int(om['jobs'])})",
            )
            notes.append(
                f"also on {other['provider']} `{other['token']}` ({int(om['jobs'])} jobs); "
                "kept the larger board"
            )
        deduped.append((best, best_m, "; ".join(notes)))
        funnel["deduped"][best["provider"]] += 1

    deduped.sort(key=lambda r: (-r[1]["us_tech"], -r[1]["jobs"], r[0]["token"].lower()))
    kept = deduped[: th.target]
    for row, m, _ in deduped[th.target :]:
        drop(
            row,
            f"below the {th.target:,}-company cut (ranked by US tech roles: {int(m['us_tech'])})",
        )

    out: list[dict[str, Any]] = []
    today = date.today().isoformat()
    for row, m, note in kept:
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
                "notes": note,
                "recon_date": today,
            }
        )
    out.sort(key=lambda r: (PROVIDERS.index(r["provider"]), str(r["company"]).lower()))
    dropped.sort(key=lambda r: (r["reason"], r["provider"], str(r["board"]).lower()))
    return out, dropped, funnel


def _source_label(sources: str) -> str:
    parts = sources.split("|")
    labels = []
    if any(s.startswith("cc:") for s in parts):
        labels.append("Common Crawl")
    if "yc" in parts:
        labels.append("YC directory")
    return " + ".join(labels) or sources


def _reason_group(reason: str) -> str:
    return re.sub(r"\s*\(.*$", "", reason).split(":")[0]


def render_sources_md(
    boards: list[dict[str, Any]],
    dropped: list[dict[str, Any]],
    funnel: dict[str, Counter[str]],
    th: Thresholds,
    harvest: dict[str, Any],
    verify: dict[str, Any],
    check_ids: list[str],
) -> str:
    totals = Counter(b["provider"] for b in boards)
    jobs: Counter[str] = Counter()
    us_jobs: Counter[str] = Counter()
    for b in boards:
        jobs[b["provider"]] += int(b["jobs_at_recon"])
        us_jobs[b["provider"]] += int(b["us_jobs_at_recon"])
    yc_misses = [
        d for d in dropped if d["reason"].startswith("board not found") and d["sources"] == "yc"
    ]
    miss_ids = {id(d) for d in yc_misses}
    listed = [d for d in dropped if id(d) not in miss_ids]
    crawls = ", ".join(f"`{c}`" for c in harvest.get("crawls", []))
    yc_log: dict[str, Any] = next(
        (e for e in harvest.get("log", []) if "companies_picked" in e), {}
    )
    lines = [
        "# Sources",
        "",
        "The tracked companies, where the candidates came from, and why every other",
        "candidate was dropped. Generated by `jobpipe recon-select` from the live checks "
        + ", ".join(f"`checks/results/{c}/`" for c in check_ids)
        + " (raw per-board results are in `verify.csv` there).",
        "",
        "## Totals per provider",
        "",
        "| Provider | Companies | Open jobs at recon | US jobs at recon |",
        "|---|---:|---:|---:|",
    ]
    for p in PROVIDERS:
        lines.append(f"| {p} | {totals.get(p, 0):,} | {jobs.get(p, 0):,} | {us_jobs.get(p, 0):,} |")
    lines += [
        f"| **total** | **{sum(totals.values()):,}** | **{sum(jobs.values()):,}** |"
        f" **{sum(us_jobs.values()):,}** |",
        "",
        "## Seed sources",
        "",
        "| Source | What it gave | Link |",
        "|---|---|---|",
        f"| Common Crawl URL index, crawls {crawls} | board names from every captured URL on"
        " boards.greenhouse.io, job-boards.greenhouse.io, jobs.lever.co and jobs.ashbyhq.com"
        " | https://index.commoncrawl.org/ |",
        "| Y Combinator company directory, via the yc-oss JSON mirror |"
        f" {yc_log.get('companies_picked', '?')} active, hiring, US companies with ≥ 15 staff"
        f" (of {yc_log.get('companies_total', '?')}); up to 3 guessed board names each, tried"
        " on all three providers | https://www.ycombinator.com/companies ,"
        " https://yc-oss.github.io/api/companies/all.json |",
        "",
        f"Harvest: {harvest.get('candidates', 0):,} distinct (provider, board) candidates."
        f" Verify: {verify.get('verified', 0):,} API calls, one per candidate.",
        "",
        "## Selection rules (approved 2026-11-03)",
        "",
        f"1. The API answered 200 with at least {th.min_jobs} listed job and at least 1 US role.",
        f"2. Mostly US: ≥ {th.min_us_share:.0%} of jobs with a known country are in the US, and"
        f" the country is known for ≥ {th.min_known_share:.0%} of jobs.",
        f"3. Tech company: ≥ {th.min_tech_share:.0%} of titles match the tech-title signal"
        " (`src/jobpipe/recon/signals.py`).",
        "4. Companies only: staffing/recruiting agencies, job aggregators and test/demo boards"
        " are dropped (rules in `src/jobpipe/recon/select.py` plus the reviewed list in"
        " `seeds/exclusions.csv`).",
        "5. One board per company: when a company is on two boards, the one with more open jobs"
        " is kept and noted.",
        f"6. At most {th.target:,} companies (ranked by US tech roles); at least"
        f" {th.minimum:,} required, all three providers represented.",
        "",
        "## Funnel",
        "",
        "| Stage | " + " | ".join(PROVIDERS) + " | Total |",
        "|---|" + "---:|" * (len(PROVIDERS) + 1),
    ]
    for stage, counts in funnel.items():
        vals = [counts.get(p, 0) for p in PROVIDERS]
        lines.append(f"| {stage} | " + " | ".join(f"{v:,}" for v in vals) + f" | {sum(vals):,} |")
    lines += [
        "",
        "## Tracked boards",
        "",
        "US share = share of jobs with a known country that are open in the US. Company names"
        " come from the Greenhouse API, the YC directory, or the board name (the Lever and Ashby"
        " APIs do not return a company name).",
        "",
        "| Provider | Board name | Company | Open jobs (recon) | US share | Notes |",
        "|---|---|---|---:|---:|---|",
    ]
    for b in boards:
        notes = [_source_label(str(b["sources"])), f"tech {float(b['tech_share']):.0%}"]
        if b["company_name_source"] != "api":
            notes.append(f"name from {b['company_name_source']}")
        if b.get("notes"):
            notes.append(str(b["notes"]))
        company = str(b["company"]).replace("|", "/")
        lines.append(
            f"| {b['provider']} | `{b['board']}` | {company} | {int(b['jobs_at_recon']):,} |"
            f" {float(b['us_share']):.0%} | {'; '.join(notes)} |"
        )
    groups = Counter(_reason_group(d["reason"]) for d in dropped)
    lines += [
        "",
        "## Dropped boards",
        "",
        "Every candidate that was not kept, with its reason. Summary:",
        "",
        "| Reason | Boards |",
        "|---|---:|",
    ]
    for reason, n in groups.most_common():
        lines.append(f"| {reason} | {n:,} |")
    lines += [
        "",
        f'{len(yc_misses):,} of the "board not found" rows are YC name guesses that do not exist'
        " on that provider. They are guesses, not boards, so they are only counted here (each one"
        " is in `verify.csv`). Every other dropped board is listed below.",
        "",
        "| Provider | Board name | Company | Jobs | US jobs | Reason |",
        "|---|---|---|---:|---:|---|",
    ]
    for d in listed:
        company = str(d["company"]).replace("|", "/")
        lines.append(
            f"| {d['provider']} | `{d['board']}` | {company} | {d['jobs']:,} | {d['us_jobs']:,} |"
            f" {d['reason']} |"
        )
    return "\n".join(lines) + "\n"


def run(
    verify_csv: Path,
    harvest_summary: dict[str, Any],
    verify_summary: dict[str, Any],
    check_ids: list[str],
    out_csv: Path,
    out_md: Path,
    th: Thresholds,
    exclusions_csv: Path = Path("seeds/exclusions.csv"),
    dropped_csv: Path | None = None,
) -> dict[str, Any]:
    rows = read_csv(verify_csv)
    boards, dropped, funnel = select(rows, th, load_exclusions(exclusions_csv))
    write_csv(out_csv, boards, BOARD_FIELDS)
    if dropped_csv is not None:
        write_csv(dropped_csv, dropped, DROPPED_FIELDS)
    out_md.write_text(
        render_sources_md(boards, dropped, funnel, th, harvest_summary, verify_summary, check_ids)
    )
    return {
        "funnel": {k: dict(v) for k, v in funnel.items()},
        "kept": len(boards),
        "by_provider": dict(Counter(b["provider"] for b in boards)),
        "dropped_reasons": dict(Counter(_reason_group(d["reason"]) for d in dropped)),
    }
