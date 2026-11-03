# Decisions

Status: draft written during step 1 (recon). Step 2 expands it.

## D-001 Sources: official public job-board APIs only (checked 2026-11-03)

| Provider | Endpoint used | Docs read | Terms read |
|---|---|---|---|
| Greenhouse | `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs` (`?content=true` in daily ingest) | https://docs.greenhouse.io/job-board.html (moved from developers.greenhouse.io) | https://www.greenhouse.com/legal, Master Subscription Agreement (last updated 2026-02-01) |
| Lever | `GET https://api.lever.co/v0/postings/{site}?mode=json` | https://github.com/lever/postings-api (README) | https://www.lever.co/legal/terms-of-service (last updated 2023-08-25) |
| Ashby | `GET https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true` | https://developers.ashbyhq.com/docs/public-job-posting-api (page updatedAt 2026-10-23) | https://www.ashbyhq.com/terms (last updated 2025-09-29), product-specific terms (2026-06-24) |

What the documents say:

- Greenhouse docs: "Job Board data is publicly available, so authentication is not required for any GET endpoints." No rate limit is documented for the Job Board API. `boards-api.greenhouse.io/robots.txt` disallows only `/embed/`, which we never call.
- Lever README: "all job postings in the `published` state are publicly viewable. These jobs may be scraped by third parties." The only documented rate limit (2 req/s) is for application POSTs. `api.lever.co/robots.txt` says `Crawl-delay: 1`, which we honour (≤ 1 request start per second to that host).
- Ashby docs: the API returns "all currently published Job Postings" for an organisation. No rate limit is documented. Responses carry `cache-control: public, max-age=60`.
- None of the three publishes API or website terms that bind a third party reading these unauthenticated GET endpoints. The legal documents found are customer agreements (MSA / ToS). Their fair-use clauses (no "excessive" or "overburdening" use, possible rate limiting, Lever's bar on direct competitors and competitive benchmarking) bind customers, but we follow their spirit anyway: one request per board per day, low per-host concurrency, an identifying User-Agent (`job-postings-pipeline/<version> (+https://siddharthkumar.com)`).
- Copyright and privacy: description text is the employer's content, and `jobs.lever.co/robots.txt` reserves AI-training rights. We never store or publish descriptions; they are read in memory only to extract structured fields, and a hash is kept for change detection. Greenhouse `metadata` holds employer-defined custom fields that can contain names, so it is dropped entirely in bronze.

## D-002 Politeness rules (implemented in `src/jobpipe/http.py`)

- Per-host concurrency cap and minimum interval between request starts: Greenhouse 4 / 0.25 s, Lever 2 / 1.0 s (crawl-delay), Ashby 3 / 0.35 s, Common Crawl index 1 / 2.0 s.
- Retries only for HTTP 429, 5xx and network/timeout errors: exponential backoff with jitter, at most 4 retries, `Retry-After` honoured.
- A block stops that host for the rest of the run. A block is any of: HTTP 403; HTTP 429 after the last retry; `Retry-After` above the cap; 20 consecutive network errors. Later requests to the host return `host_blocked` without touching the network.
- 404/410 means the board does not exist (or no longer exists) and is never retried.

## D-003 Live checks run on GitHub Actions

The development sandbox is not used to call the job boards. Every live call runs in `.github/workflows/checks.yml`, triggered by a push that changes `checks/request.yml`; the workflow commits `checks/results/<id>/` back to the branch. Only commands whitelisted in `src/jobpipe/checks.py` can run.

## D-004 Recon seed sources

See `docs/sources.md` for the funnel. Seed sources:

1. Common Crawl URL index (https://index.commoncrawl.org/): every captured URL under `boards.greenhouse.io`, `job-boards.greenhouse.io`, `jobs.lever.co` and `jobs.ashbyhq.com` in the latest crawls. The board name is the first path segment (or `for=` on Greenhouse embed URLs). Capture count is kept as `cc_hits`.
2. Y Combinator company directory (https://www.ycombinator.com/companies), read through the yc-oss JSON mirror (https://yc-oss.github.io/api/companies/all.json). Active, hiring, US-region companies with team size ≥ 15 give guessed board names (website domain label, compacted name, hyphenated name), which the verify step tries on each provider.

## D-005 Stack versions (PyPI, checked 2026-11-03)

| Package | Version | License |
|---|---|---|
| Python | 3.12 | PSF |
| uv | 0.11.x | MIT / Apache-2.0 |
| httpx | 0.28.1 | BSD-3-Clause |
| pydantic | 2.14.2 | MIT |
| PyYAML | 6.0.3 | MIT |
| duckdb | 2.0.0 (to be confirmed against dbt-duckdb) | MIT |
| dbt-core | 1.12.6 | Apache-2.0 |
| dbt-duckdb | 1.11.1 | Apache-2.0 |
| pyarrow | 26.0.1 | Apache-2.0 |
| ruff | 0.17.3 | MIT |
| mypy | 2.4.1 | MIT |
| pytest | 9.2.0 | MIT |
| pip-audit | 2.10.1 | Apache-2.0 |
| huggingface-hub | 2.4.0 | Apache-2.0 |

GitHub Actions are pinned by commit SHA: actions/checkout v7.0.1, astral-sh/setup-uv v10.3.3.
