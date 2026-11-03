"""Live-check runner used by .github/workflows/checks.yml.

The sandbox used for development cannot reach the job boards, so every live
check is described in ``checks/request.yml``, executed on GitHub Actions and
its results are committed under ``checks/results/<id>/``.

Only commands listed in ``COMMANDS`` can run.
"""

from __future__ import annotations

import json
import os
import platform
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from jobpipe.csvio import read_csv, write_csv

RESULTS_DIR = Path("checks/results")


def _recon_harvest(params: dict[str, Any], out: Path) -> dict[str, Any]:
    from jobpipe.recon import seeds

    rows, summary = seeds.run(
        crawls=int(params.get("crawls", 3)),
        max_pages=int(params.get("max_pages", 200)),
        yc_min_team=int(params.get("yc_min_team", 15)),
    )
    write_csv(out / "seeds_raw.csv", rows, ["provider", "token", "sources", "cc_hits",
                                            "yc_name", "yc_slug"])  # fmt: skip
    return summary


def _recon_cc_pages(params: dict[str, Any], out: Path) -> dict[str, Any]:
    """How many index pages each pattern has in the latest crawls (sizing only)."""
    import asyncio
    import json as _json

    from jobpipe.recon import seeds

    async def go() -> dict[str, Any]:
        result: dict[str, Any] = {}
        async with seeds.make_client() as client:
            crawls = await seeds.latest_crawls(client, int(params.get("crawls", 3)))
            for crawl in crawls:
                for pattern in seeds.CC_PATTERNS:
                    res = await client.get_text(
                        f"{seeds.CC_INDEX}/{crawl}-index",
                        {"url": pattern, "output": "json", "showNumPages": "true"},
                    )
                    result[f"{crawl} {pattern}"] = (
                        _json.loads(res.data) if res.ok else f"{res.outcome} {res.error}"
                    )
            result["http"] = client.stats_summary()
        return result

    return asyncio.run(go())


def select_for_verify(rows: list[dict[str, str]], params: dict[str, Any]) -> list[dict[str, str]]:
    """Pick which harvested candidates to verify (documented in docs/decisions.md)."""
    min_hits = int(params.get("min_cc_hits", 1))
    cap = int(params.get("max_per_provider", 100_000))
    include_yc = bool(params.get("include_yc", True))
    picked: list[dict[str, str]] = []
    per: dict[str, int] = {}
    for r in sorted(rows, key=lambda r: -int(r["cc_hits"] or 0)):
        from_cc = int(r["cc_hits"] or 0) >= min_hits
        from_yc = include_yc and "yc" in r["sources"].split("|")
        if not (from_cc or from_yc):
            continue
        if from_cc and not from_yc:
            if per.get(r["provider"], 0) >= cap:
                continue
            per[r["provider"]] = per.get(r["provider"], 0) + 1
        picked.append(r)
    return picked


def _recon_verify(params: dict[str, Any], out: Path) -> dict[str, Any]:
    from jobpipe.recon import verify

    rows = read_csv(Path(params["input"]))
    picked = select_for_verify(rows, params)
    results, summary = verify.run(picked, budget_minutes=float(params.get("budget_minutes", 300)))
    write_csv(out / "verify.csv", results, verify.FIELDS)
    summary["selection"] = {k: v for k, v in params.items() if k != "input"}
    summary["input"] = params["input"]
    return summary


FREE_TEXT_KEYS = {
    # Greenhouse
    "content", "metadata", "questions", "location_questions", "compliance",
    "demographic_questions", "data_compliance", "pay_input_ranges",
    # Lever
    "description", "descriptionPlain", "descriptionBody", "descriptionBodyPlain", "lists",
    "additional", "additionalPlain", "opening", "openingPlain",
    # Ashby
    "descriptionHtml", "descriptionSocial",
}  # fmt: skip
SYNTHETIC_DESCRIPTION = (
    "SYNTHETIC FIXTURE TEXT (the real description is never stored). Hybrid: 3 days a week in "
    "the office. 5+ years of experience. The base salary range is $120,000 - $150,000 per year."
)


def sanitise_job(provider: str, job: dict[str, Any]) -> dict[str, Any]:
    """Drop free text and employer-defined fields; insert a marked synthetic description."""
    clean = {k: v for k, v in job.items() if k not in FREE_TEXT_KEYS}
    if provider == "greenhouse":
        clean["content"] = SYNTHETIC_DESCRIPTION
        clean["metadata"] = None
    elif provider == "lever":
        clean["descriptionPlain"] = SYNTHETIC_DESCRIPTION
        clean["lists"] = []
    else:
        clean["descriptionPlain"] = SYNTHETIC_DESCRIPTION
    return clean


def _capture_fixtures(params: dict[str, Any], out: Path) -> dict[str, Any]:
    """Golden fixtures: a few real postings per board, sanitised (see sanitise_job)."""
    import asyncio
    import json as _json

    from jobpipe.http import PoliteClient
    from jobpipe.ingest import HOST_POLICIES
    from jobpipe.providers import get_provider

    max_jobs = int(params.get("max_jobs", 4))
    boards = list(params.get("boards") or [])

    async def go() -> dict[str, Any]:
        written: dict[str, Any] = {}
        async with PoliteClient(host_policies=HOST_POLICIES) as client:
            for b in boards:
                provider = get_provider(b["provider"])
                res = await client.get_json(
                    provider.board_url(b["board"]), provider.ingest_params()
                )
                if not res.ok:
                    written[f"{b['provider']}/{b['board']}"] = f"{res.outcome} {res.status}"
                    continue
                jobs = provider.jobs(res.data)[:max_jobs]
                payload: Any
                if provider.name == "lever":
                    payload = [sanitise_job("lever", j) for j in jobs]
                else:
                    payload = {"jobs": [sanitise_job(provider.name, j) for j in jobs]}
                    if provider.name == "greenhouse":
                        payload["meta"] = {"total": len(jobs)}
                    else:
                        payload["apiVersion"] = (res.data or {}).get("apiVersion", "1")
                path = out / "fixtures" / provider.name / f"{b['board']}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(_json.dumps(payload, indent=2, sort_keys=True) + "\n")
                written[f"{b['provider']}/{b['board']}"] = len(jobs)
        return written

    return {"written": asyncio.run(go())}


COMMANDS: dict[str, Callable[[dict[str, Any], Path], dict[str, Any]]] = {
    "capture-fixtures": _capture_fixtures,
    "recon-cc-pages": _recon_cc_pages,
    "recon-harvest": _recon_harvest,
    "recon-verify": _recon_verify,
}


def run_request(path: Path) -> int:
    req = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    check_id = str(req.get("id") or "").strip()
    command = str(req.get("command") or "").strip()
    if not check_id or "/" in check_id or check_id.startswith("."):
        raise SystemExit(f"invalid check id {check_id!r}")
    out = RESULTS_DIR / check_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "request.yml").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    meta: dict[str, Any] = {
        "id": check_id,
        "command": command,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_sha": os.environ.get("GITHUB_SHA", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "runner": f"{platform.system()} {platform.machine()} py{platform.python_version()}",
    }
    t0 = time.monotonic()
    status = 0
    steps = req.get("steps") or [{"command": command, "params": req.get("params") or {}}]
    try:
        results = []
        for step in steps:
            fn = COMMANDS.get(str(step.get("command")))
            if fn is None:
                raise ValueError(
                    f"unknown command {step.get('command')!r}; allowed: {sorted(COMMANDS)}"
                )
            results.append(fn(dict(step.get("params") or {}), out))
        meta["result"] = results[0] if len(results) == 1 else results
        meta["status"] = "ok"
    except Exception as exc:  # the result must be committed even when the check fails
        meta["status"] = "error"
        meta["error"] = f"{type(exc).__name__}: {exc}"
        meta["traceback"] = traceback.format_exc()[-4000:]
        status = 1
    meta["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    meta["duration_s"] = round(time.monotonic() - t0, 1)
    (out / "summary.json").write_text(json.dumps(meta, indent=2, default=str) + "\n")
    print(json.dumps({k: meta[k] for k in ("id", "status", "duration_s")}))
    return status
