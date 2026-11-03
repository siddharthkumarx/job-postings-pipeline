"""Harvest candidate board names from public sources.

Sources (recorded per candidate in the ``sources`` column):

* ``cc:<crawl-id>`` - the Common Crawl URL index (https://index.commoncrawl.org/),
  queried for every captured URL under the hosted job-board domains of the three
  providers. The first path segment of a captured URL is the board name.
* ``yc`` - the Y Combinator company directory (https://www.ycombinator.com/companies)
  as published in machine-readable form by the yc-oss project
  (https://yc-oss.github.io/api/companies/all.json). Active, hiring US companies
  give guessed board names (website domain label and normalised company name),
  which the verify step then confirms or rejects against each provider's API.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from jobpipe.http import HostPolicy, PoliteClient

CC_INDEX = "https://index.commoncrawl.org"
YC_DIRECTORY = "https://yc-oss.github.io/api/companies/all.json"

# Hosted job-board domains -> provider.
CC_PATTERNS: dict[str, str] = {
    "boards.greenhouse.io/*": "greenhouse",
    "job-boards.greenhouse.io/*": "greenhouse",
    "jobs.lever.co/*": "lever",
    "jobs.ashbyhq.com/*": "ashby",
}

RESERVED = {
    "embed", "v1", "api", "static", "assets", "images", "img", "favicon.ico", "robots.txt",
    "sitemap.xml", "sitemap", "job_app", "jobs", "boards", "include", "login", "users",
    "my_applications", "_next", "b", "meeting", "apply", "search", "careers", "css", "js",
    "fonts", "privacy", "terms", "cdn-cgi", "well-known", ".well-known", "null", "undefined",
    "index.html", "favicon.png", "apple-touch-icon.png", "manifest.json",
}  # fmt: skip
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\- ]{0,79}$")


def token_from_url(url: str, provider: str) -> str | None:
    """Board name from a hosted job-board URL, or None for non-board URLs."""
    try:
        parts = urlsplit(url if "://" in url else f"https://{url}")
    except ValueError:
        return None
    segments = [unquote(s) for s in parts.path.split("/") if s]
    token: str | None = None
    if provider == "greenhouse" and segments and segments[0] == "embed":
        qs = parse_qs(parts.query)
        values = qs.get("for") or []
        token = values[0] if values else None
    elif segments:
        token = segments[0]
    if not token:
        return None
    token = token.strip()
    if token.lower() in RESERVED or not TOKEN_RE.match(token):
        return None
    if provider in ("greenhouse", "lever"):
        token = token.lower()
    return token


@dataclass
class Candidate:
    provider: str
    token: str
    sources: set[str] = field(default_factory=set)
    cc_hits: int = 0
    yc_name: str | None = None
    yc_slug: str | None = None


class SeedSet:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], Candidate] = {}
        self._casing: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)

    def add(
        self,
        provider: str,
        token: str,
        source: str,
        *,
        hits: int = 0,
        yc_name: str | None = None,
        yc_slug: str | None = None,
    ) -> None:
        key = (provider, token.lower())
        cand = self._items.get(key)
        if cand is None:
            cand = Candidate(provider=provider, token=token)
            self._items[key] = cand
        self._casing[key][token] += max(hits, 1)
        cand.sources.add(source)
        cand.cc_hits += hits
        if yc_name and not cand.yc_name:
            cand.yc_name, cand.yc_slug = yc_name, yc_slug

    def rows(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for key, cand in self._items.items():
            token = self._casing[key].most_common(1)[0][0]
            out.append(
                {
                    "provider": cand.provider,
                    "token": token,
                    "sources": "|".join(sorted(cand.sources)),
                    "cc_hits": cand.cc_hits,
                    "yc_name": cand.yc_name or "",
                    "yc_slug": cand.yc_slug or "",
                }
            )
        out.sort(key=lambda r: (str(r["provider"]), -int(r["cc_hits"]), str(r["token"]).lower()))
        return out

    def __len__(self) -> int:
        return len(self._items)


def make_client() -> PoliteClient:
    return PoliteClient(
        host_policies={
            # The Common Crawl index is a shared, often busy service: one request at a time.
            "index.commoncrawl.org": HostPolicy(concurrency=1, min_interval_s=2.0),
            "yc-oss.github.io": HostPolicy(concurrency=1, min_interval_s=1.0),
        },
        timeout_s=120.0,
        max_retries=5,
        max_backoff_s=90.0,
        max_retry_after_s=300.0,
        block_after_network_errors=8,
    )


async def latest_crawls(client: PoliteClient, n: int) -> list[str]:
    res = await client.get_json(f"{CC_INDEX}/collinfo.json")
    if not res.ok or not isinstance(res.data, list):
        raise RuntimeError(f"collinfo.json failed: {res.outcome} {res.error}")
    return [str(c["id"]) for c in res.data[:n]]


async def harvest_common_crawl(
    client: PoliteClient,
    seeds: SeedSet,
    crawls: list[str],
    max_pages: int,
    log: list[dict[str, Any]],
    budget_s: float = 3 * 3600,
) -> None:
    deadline = time.monotonic() + budget_s
    for crawl in crawls:
        if time.monotonic() > deadline:
            log.append({"crawl": crawl, "skipped": "time budget exhausted"})
            continue
        endpoint = f"{CC_INDEX}/{crawl}-index"
        for pattern, provider in CC_PATTERNS.items():
            entry: dict[str, Any] = {"crawl": crawl, "pattern": pattern, "pages": 0, "urls": 0}
            meta = await client.get_text(
                endpoint, {"url": pattern, "output": "json", "showNumPages": "true"}
            )
            if not meta.ok:
                entry["error"] = f"{meta.outcome} {meta.status} {meta.error}"
                log.append(entry)
                continue
            try:
                total_pages = int(json.loads(meta.data).get("pages", 0))
            except (ValueError, AttributeError):
                total_pages = 0
            entry["pages_available"] = total_pages
            hits: Counter[str] = Counter()
            for page in range(min(total_pages, max_pages)):
                print(f"cc {crawl} {pattern} page {page + 1}/{total_pages}", flush=True)
                res = await client.get_text(
                    endpoint,
                    {"url": pattern, "output": "json", "fl": "url", "page": str(page)},
                )
                if not res.ok:
                    entry.setdefault("page_errors", []).append(
                        f"{page}: {res.outcome} {res.status} {res.error}"
                    )
                    if res.outcome == "host_blocked":
                        break
                    continue
                entry["pages"] += 1
                for line in str(res.data).splitlines():
                    try:
                        url = json.loads(line)["url"]
                    except (ValueError, KeyError, TypeError):
                        continue
                    entry["urls"] += 1
                    tok = token_from_url(url, provider)
                    if tok:
                        hits[tok] += 1
            for tok, n in hits.items():
                seeds.add(provider, tok, f"cc:{crawl}", hits=n)
            entry["tokens"] = len(hits)
            log.append(entry)
            if client.is_blocked("index.commoncrawl.org"):
                return


_NAME_CLEAN = re.compile(r"[^a-z0-9]+")
_DOMAIN_LABEL = re.compile(r"^(?:www\.)?([a-z0-9-]+)\.")


def yc_guesses(company: dict[str, Any]) -> list[str]:
    guesses: list[str] = []
    website = str(company.get("website") or "").lower()
    host = urlsplit(website if "://" in website else f"https://{website}").hostname or ""
    m = _DOMAIN_LABEL.match(host)
    if m:
        guesses.append(m.group(1))
    name = str(company.get("name") or "").lower()
    compact = _NAME_CLEAN.sub("", name)
    if compact:
        guesses.append(compact)
    hyphen = _NAME_CLEAN.sub("-", name).strip("-")
    if hyphen and hyphen != compact:
        guesses.append(hyphen)
    seen: list[str] = []
    for g in guesses:
        if g and g not in seen and TOKEN_RE.match(g):
            seen.append(g)
    return seen[:3]


def yc_is_candidate(company: dict[str, Any], min_team: int) -> bool:
    if str(company.get("status") or "").lower() != "active":
        return False
    if company.get("isHiring") is False:
        return False
    regions = [str(r).lower() for r in company.get("regions") or []]
    locs = str(company.get("all_locations") or "").lower()
    in_us = any("united states" in r for r in regions) or "usa" in locs
    team = company.get("team_size") or 0
    return in_us and isinstance(team, int) and team >= min_team


async def harvest_yc(
    client: PoliteClient, seeds: SeedSet, min_team: int, log: list[dict[str, Any]]
) -> None:
    res = await client.get_json(YC_DIRECTORY)
    entry: dict[str, Any] = {"source": YC_DIRECTORY}
    if not res.ok or not isinstance(res.data, list):
        entry["error"] = f"{res.outcome} {res.status} {res.error}"
        log.append(entry)
        return
    picked = [c for c in res.data if isinstance(c, dict) and yc_is_candidate(c, min_team)]
    entry.update({"companies_total": len(res.data), "companies_picked": len(picked)})
    pairs = 0
    for c in picked:
        for guess in yc_guesses(c):
            for provider in ("greenhouse", "lever", "ashby"):
                seeds.add(
                    provider, guess, "yc", yc_name=str(c.get("name")), yc_slug=str(c.get("slug"))
                )
                pairs += 1
    entry["guess_pairs"] = pairs
    log.append(entry)


async def harvest(
    *, crawls: int = 3, max_pages: int = 200, yc_min_team: int = 15, budget_minutes: float = 180
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    seeds = SeedSet()
    log: list[dict[str, Any]] = []
    async with make_client() as client:
        crawl_ids: list[str] = []
        try:
            crawl_ids = await latest_crawls(client, crawls)
        except RuntimeError as exc:
            log.append({"source": "commoncrawl", "error": str(exc)})
        if crawl_ids:
            await harvest_common_crawl(
                client, seeds, crawl_ids, max_pages, log, budget_s=budget_minutes * 60
            )
        await harvest_yc(client, seeds, yc_min_team, log)
        stats = client.stats_summary()
    rows = seeds.rows()
    by_provider = Counter(r["provider"] for r in rows)
    summary = {
        "crawls": crawl_ids,
        "candidates": len(rows),
        "by_provider": dict(by_provider),
        "log": log,
        "http": stats,
    }
    return rows, summary


def run(**kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return asyncio.run(harvest(**kwargs))
