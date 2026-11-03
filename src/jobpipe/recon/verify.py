"""Verify candidate boards against the official APIs and compute selection signals.

For each (provider, board) one GET is made. Nothing from the response is kept
except counts (jobs, US jobs, tech jobs …) and the company display name the
Greenhouse API returns. No description text or personal data is written.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from typing import Any

from jobpipe.geo import job_countries
from jobpipe.http import HostPolicy, PoliteClient
from jobpipe.providers import get_provider
from jobpipe.recon.signals import is_tech_title

# Lever's api.lever.co/robots.txt asks for Crawl-delay: 1, so one request start per second.
HOST_POLICIES = {
    "boards-api.greenhouse.io": HostPolicy(concurrency=4, min_interval_s=0.25),
    "api.lever.co": HostPolicy(concurrency=2, min_interval_s=1.0),
    "api.ashbyhq.com": HostPolicy(concurrency=3, min_interval_s=0.35),
}

FIELDS = [
    "provider", "token", "sources", "cc_hits", "yc_name", "outcome", "status", "company_name",
    "jobs", "us_jobs", "non_us_jobs", "unknown_jobs", "tech_jobs", "us_tech_jobs",
    "remote_jobs", "top_countries", "bytes", "attempts",
]  # fmt: skip


def summarise(provider_name: str, payload: Any) -> dict[str, Any]:
    provider = get_provider(provider_name)
    jobs = provider.jobs(payload)
    countries: Counter[str] = Counter()
    us = non_us = unknown = tech = us_tech = remote = 0
    for raw in jobs:
        job = provider.recon_job(raw)
        cs = job_countries(job.locations, job.country_hints)
        tech_title = is_tech_title(job.title)
        tech += tech_title
        if (job.workplace or "").lower() == "remote":
            remote += 1
        if not cs:
            unknown += 1
        elif "US" in cs:
            us += 1
            us_tech += tech_title
        else:
            non_us += 1
        countries.update(cs)
    return {
        "company_name": provider.company_name(payload) or "",
        "jobs": len(jobs),
        "us_jobs": us,
        "non_us_jobs": non_us,
        "unknown_jobs": unknown,
        "tech_jobs": tech,
        "us_tech_jobs": us_tech,
        "remote_jobs": remote,
        "top_countries": "|".join(f"{c}:{n}" for c, n in countries.most_common(5)),
    }


async def verify_one(client: PoliteClient, cand: dict[str, Any]) -> dict[str, Any]:
    provider = get_provider(str(cand["provider"]))
    res = await client.get_json(provider.board_url(str(cand["token"])), provider.params())
    row: dict[str, Any] = {k: cand.get(k, "") for k in ("provider", "token", "sources", "cc_hits")}
    row["yc_name"] = cand.get("yc_name", "")
    row.update(
        {"outcome": res.outcome, "status": res.status or "", "bytes": res.bytes,
         "attempts": res.attempts}
    )  # fmt: skip
    if res.ok:
        row.update(summarise(provider.name, res.data))
        res.data = None  # drop the payload (descriptions) as soon as it is summarised
    return row


async def verify(
    candidates: list[dict[str, Any]], *, budget_minutes: float = 300.0
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    deadline = time.monotonic() + budget_minutes * 60
    rows: list[dict[str, Any]] = []
    skipped = 0
    async with PoliteClient(host_policies=HOST_POLICIES, timeout_s=60.0) as client:
        gate = asyncio.Semaphore(16)

        async def guarded(c: dict[str, Any]) -> dict[str, Any] | None:
            nonlocal skipped
            async with gate:
                if time.monotonic() > deadline:
                    skipped += 1
                    return None
                return await verify_one(client, c)

        for fut in asyncio.as_completed([guarded(c) for c in candidates]):
            row = await fut
            if row is not None:
                rows.append(row)
        stats = client.stats_summary()
    rows.sort(key=lambda r: (r["provider"], str(r["token"]).lower()))
    summary = {
        "candidates": len(candidates),
        "verified": len(rows),
        "skipped_budget": skipped,
        "outcomes": dict(Counter(f"{r['provider']}:{r['outcome']}" for r in rows)),
        "http": stats,
    }
    return rows, summary


def run(
    candidates: list[dict[str, Any]], **kwargs: Any
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return asyncio.run(verify(candidates, **kwargs))
