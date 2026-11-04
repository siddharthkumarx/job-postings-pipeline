# Decisions

Each decision states what was chosen and why. Add new ones at the end; never renumber.

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
| duckdb | 2.0.0 (works with dbt-duckdb 1.11.1, verified by the fixture build) | MIT |
| dbt-core | 1.12.6 | Apache-2.0 |
| dbt-duckdb | 1.11.1 | Apache-2.0 |
| pyarrow | 26.0.1 | Apache-2.0 |
| ruff | 0.17.3 | MIT |
| mypy | 2.4.1 | MIT |
| pytest | 9.2.0 | MIT |
| pip-audit | 2.10.1 | Apache-2.0 |
| huggingface-hub | 2.4.0 | Apache-2.0 |

GitHub Actions are pinned by commit SHA: actions/checkout v7.0.1, astral-sh/setup-uv v10.3.3, actions/upload-artifact v7.0.2, actions/upload-pages-artifact v5.0.0, actions/deploy-pages v5.0.1. gitleaks v8.30.1 (MIT) runs as the release binary, checksum-verified, instead of the action, which needs a licence key for organisations.

dbt now advertises "dbt v2" as the default for new installs. The brief specifies dbt-core + dbt-duckdb, so this project stays on dbt Core 1.12 (Apache-2.0) with dbt-duckdb 1.11. Fonts: Instrument Sans and IBM Plex Mono, both SIL OFL 1.1, from @fontsource 5.3.0 (WOFF2 latin subsets, licences shipped next to the files).

## D-006 Role taxonomy and seniority (versioned)

- `dbt/seeds/role_taxonomy.csv` lists `taxonomy_version, priority, role_family, pattern` (case-insensitive regex on the title). The lowest priority that matches wins; no match gives `other`. Specific families come before generic ones (e.g. `analytics engineer` before `data analyst` before `analyst`).
- `dbt/seeds/seniority_rules.csv` lists `taxonomy_version, priority, seniority, pattern`. Levels: `intern`, `junior`, `mid`, `senior`, `staff_principal`, `manager`, `director`, `vp_exec`. No match gives `mid`, with `seniority_source = default`.
- When the title has no seniority signal, the description hint extracted during ingest (`desc_seniority_hint`, e.g. "5+ years") is used, with `seniority_source = description`.
- The version is a date string (`2026-11-03`), stored on every silver row (`taxonomy_version`). A change to a seed bumps the version, and `docs/decisions.md` gets a line describing it. `int_title_labels` is incremental (only new titles are matched, because the regex join took 71 s for one day's 40k titles), so a taxonomy change must be followed by `jobpipe rebuild` (full refresh) to re-label history.
- The "data roles" mart covers `data_engineer`, `analytics_engineer`, `data_analyst`, `ml_engineer` (`data_scientist` is shown alongside but is not part of the four).

## D-007 Where state lives: GitHub Release assets

- **Bronze (truth)**: one Release per month (`bronze-YYYY-MM`), assets `postings_D.parquet`, `board_runs_D.parquet` and `fx_D.parquet` (D = run date). A re-run replaces that day's assets, so runs are idempotent. Assets are durable, versioned by name, up to 2 GB each, outside git history, and downloadable by anyone once the repo is public.
- **Warehouse cache**: Release `state`, asset `warehouse.duckdb.gz`, plus `state.json` (last good run date, schema version, list of bronze dates loaded). Uploaded only after a published run, so it always holds the last good build. Before upload the file is checkpointed (`FORCE CHECKPOINT`) and validated: all required tables are present, and every loaded bronze date is in silver. After download it is validated again. If it is missing, corrupt or incomplete, the run rebuilds from every bronze asset (`jobpipe rebuild` does the same on demand).
- **Small public outputs** (`public/runs.jsonl`, `public/status.json`, `public/summary/*.csv`): committed to git by the daily run. They are tiny, diffable, and drive the shields.io badges through raw URLs.
- Rejected: **git** for bronze (about 5 MB a day would bloat history past 1 GB a year and break the 50 MB per-file rule within months); **Actions cache** as the only store (evicted after 7 days without access, 10 GB cap, not public). The Actions cache is used only to speed up uv.

## D-008 FX reference rates

ECB euro foreign exchange reference rates (https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html), full history file `eurofxref-hist.zip`, fetched on every run and stored as bronze fx. USD per unit of currency X on day d = `USD_rate(d) / X_rate(d)` (both quoted per EUR). A salary converts at the latest ECB business day on or before the posting's `first_seen` date, so a posting keeps a stable USD value. Currencies the ECB does not quote keep `salary_*_usd = null` and `fx_rate_date = null`. The original currency, period and amounts are always kept.

## D-009 Daily run-time budget (< 45 min, Lever at 1 request/s)

The estimate uses request timings measured in `checks/results/recon-verify-001/verify.csv` for the 1,500 tracked boards (one GET each, on Actions runners). Throughput per host = min(1 / interval, concurrency / mean latency), and hosts run in parallel:

| Host | Boards | Policy | Mean / p95 latency | Payload (recon) | Fetch time | With 3× latency |
|---|---:|---|---|---|---:|---:|
| Greenhouse | 779 | 4 concurrent, 0.25 s spacing | 0.56 s / 1.01 s | 37 MB | 3.2 min | 5.5 min |
| Lever | 52 | 2 concurrent, 1.0 s spacing (≤ 1 req/s) | 2.62 s / 10.4 s | 45 MB | 1.1 min | 3.4 min |
| Ashby | 669 | 3 concurrent, 0.35 s spacing | 0.64 s / 1.09 s | 250 MB | 3.9 min | 7.1 min |

The daily ingest asks Greenhouse for `content=true` and Ashby for compensation, so payloads grow. The "3× latency" column covers that and still gives under 8 minutes of fetching. Adding warehouse restore and upload (< 2 min), the dbt build (2–4 min at this size) and publishing (< 3 min), the estimate is about **15–20 minutes** per full daily run. The step timeout is 60 min and the job timeout 75 min. A failed host never stalls the run, because blocks short-circuit. The first real daily runs check this estimate; their durations go to `public/runs.jsonl` (`duration_s`, `ingest.duration_s`).

## D-010 Bronze schema and privacy

The Pydantic model `jobpipe.models.Posting` (schema_version 1) is the only shape that reaches disk. Fields are listed in `docs/architecture.md`. Each adapter builds a `Posting` from an explicit allowlist of API fields (no `**raw`), so a new API field never leaks into storage by accident. Description text (Greenhouse `content`, Lever `description*`/`lists`/`additional`, Ashby `description*`) is passed to `jobpipe.extract` in memory, which returns only salary, remote and seniority hints, the SHA-256 hash and the character count. Anything that looks like an email or phone number is never extracted.

## D-011 Lifecycle definitions

- `first_seen` / `last_seen`: first and last run date the posting was listed.
- A posting is **closed** when it has been missing from **2 consecutive runs in which its board was fetched successfully** (`board_runs.status = ok`). Failed board fetches never count as absences. `closed_on` is the first missing run date. A posting that reappears after closing reopens: the same `posting_key` continues and `reopened_count` increments.
- `days_open` = `last_seen - first_seen + 1` for closed postings, `run_date - first_seen + 1` for open ones. Postings already open on the first run are flagged `left_censored = true` and excluded from days-open bands.
- SCD2 tracks `title`, `location_raw` and the salary tuple (min, max, currency, period). A new version starts on the first run date where the tracked hash differs. `valid_to` is exclusive, and `is_current` marks the latest version.

## D-012 Quality gates and holds

- dbt tests (unique, not_null, accepted_values, relationships, plus custom range tests) run in `dbt build`. Any error fails the build, and the run is **held**.
- Source freshness: bronze `fetched_at` must be < 36 h old (error) or < 26 h (warn).
- Guards (`jobpipe.guards`), measured against the last published run:
  - open postings must not change by more than ±35 %;
  - boards fetched OK ≥ 90 % of tracked boards;
  - null rate thresholds: `title` 0 %, `job_url` 0 %, `company` 0 %, `location_raw` ≤ 10 %, `role_family` (not null; `other` ≤ 40 %), `country` unknown ≤ 25 %.
- A held run keeps the last good marts published, appends `status: held` with reasons to `runs.jsonl`, and opens or updates a `pipeline-alert` issue. Its bronze is still stored, because it is raw truth. `jobpipe release-hold --date D` lets a human accept a held run, for example a genuine mass closing.
- Contracts: public marts use dbt `contract: {enforced: true}` with declared column types; a breaking change needs a new model version (see `docs/data-contracts.md`).

## D-013 Dashboard

Static HTML generated by Python (`jobpipe.site`), with charts drawn as inline SVG at build time, so no client-side charting library or external script is needed. A small inline script only handles tab switching, and the page works without it. Fonts are self-hosted WOFF2 subsets of Instrument Sans and IBM Plex Mono (both SIL OFL 1.1), from the @fontsource npm packages. Colours come from the brief, and every text/background pair is checked for ≥ 4.5:1 contrast in a unit test (`tests/test_site.py`). The dataviz palette validator, run on teal vs amber over the panel colour, passes CVD separation (ΔE 13.4 protan) and contrast. It flags both colours as brighter than its dark-mode lightness band; they are the brand colours from the brief, so they stay, and every two-series chart also carries a legend and a table view. Charts are mostly single-series teal, and amber marks the thing to look at (data roles, closed roles).

## D-014 Board selection rules (approved 2026-11-03)

Selection runs in `jobpipe.recon.select` over `checks/results/recon-verify-001/verify.csv`:
1. HTTP 200 with ≥ 1 listed job and ≥ 1 US job.
2. Mostly US: ≥ 50 % of jobs with a known country are in the US, and the country is known for ≥ 50 % of jobs.
3. Tech company: ≥ 40 % of titles match the broad tech-title signal. At 20 %, clearly non-tech organisations got in (a civil-liberties NGO, a sports league, a live-events company). At 40 %, the companies at the boundary are tech companies (Datadog, Samsara, Rubrik), and 2,054 boards still pass, so the 1,500 cut still applies.
4. Companies only: staffing/recruiting agencies, job aggregators (VC or venture-studio portfolio boards, talent pools, placement boards) and test/demo boards are dropped. Narrow name rules catch the obvious cases; a manual review of the kept list is recorded in `seeds/exclusions.csv`. A company's own board named "X Careers" or "X Job Board" is not an aggregator. Separately branded subsidiaries with their own board (e.g. Samsung Semiconductor vs Samsung Research America, the Fanatics business units) count as companies.
5. One board per company (normalised company name, plus the reviewed same-company pairs in `seeds/exclusions.csv`). The board with more open jobs wins, and the other is listed as dropped ("duplicate: …").
6. At least 1,000 companies, target 1,500, all three providers represented. 2,665 → 2,054 boards passed rules 1–5, and the 1,500 with the most US tech roles were kept: Greenhouse 779, Ashby 669, Lever 52. Lever is small because the Common Crawl index returned few Lever pages (see `docs/incidents.md`).
7. Display names: the Greenhouse API returns a company name, but Lever and Ashby do not. For those boards the name comes from the YC directory when matched, otherwise from the board name (CamelCase split, domain suffix and corporate suffix dropped, known endings such as "ai" or "health" split off). A reviewed list in `seeds/company_names.csv` fixes brand casing (OpenAI, 1Password, ClickUp …).

## D-015 Run ledger is append-only

`public/runs.jsonl` keeps every attempt (failed, held and published), one line each. `status.json` counts the final attempt of each run date for `runs_published`, `runs_held`, `runs_failed` and `missed_runs`, and reports `attempts`, `failed_attempts` and `held_attempts` separately, so a re-run never hides an earlier failure. The first day's three attempts (failed, held, published) were restored from git history when this changed.
