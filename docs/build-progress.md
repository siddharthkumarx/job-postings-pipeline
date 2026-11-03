# Build progress

Update this file after every item: set the status, add the commit and a one-line note.
Status: `todo` · `doing` · `done` · `blocked`.

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Repo skeleton: uv project, ruff/mypy/pytest, commit-msg hook, CI commit-message job | done | `.githooks/commit-msg`, `scripts/check_commit_messages.py` |
| 2 | Polite HTTP client (per-host cap + delay, retry 429/5xx/network, Retry-After, block stops host) | done | `src/jobpipe/http.py`, `tests/test_http.py` |
| 3 | Live-check workflow (`checks/request.yml` → `checks/results/<id>/`) | done | `.github/workflows/checks.yml`, `src/jobpipe/checks.py` |
| 4 | Recon: harvest seeds (Common Crawl index, YC directory), verify via APIs, select boards, `docs/sources.md` | doing | rules approved by the owner; see `docs/sources.md` |
| 5 | Step-2 docs: docs/maintainers.md, architecture, build-progress, decisions, data-contracts, incidents | doing | |
| 6 | Golden fixtures per provider (captured by a live check, sanitised) | todo | `tests/fixtures/<provider>/*.json`; no description text kept |
| 7 | Bronze model + adapters: Pydantic `Posting`, one adapter per provider, description extraction in memory | todo | `models.py`, `extract.py`, `providers/*` |
| 8 | Ingest: run all boards → bronze Parquet (postings + board log), run manifest | todo | `ingest.py` |
| 9 | FX: ECB reference rates → bronze fx | todo | `fx.py` |
| 10 | State: GitHub Release assets sync (bronze, warehouse snapshot, state.json), rebuild from bronze | todo | `state.py` |
| 11 | dbt project + staging (silver): dedupe, role taxonomy, seniority, location, salary + USD | todo | `dbt/models/staging` |
| 12 | History: first/last seen, closed (2 missed fetches), days open, SCD2 (title, location, salary) | todo | `dbt/models/intermediate` |
| 13 | Marts (gold): fct_job_postings, dim_company, weekly open roles, days-open + salary bands, velocity, data roles | todo | `dbt/models/marts` |
| 14 | Quality: dbt tests, source freshness, guards (row count, null rate), contracts, hold logic | todo | `guards.py`, `docs/data-contracts.md` |
| 15 | Orchestration: `jobpipe run`, `backfill --from --to`, `rebuild`; idempotency | todo | `cli.py`, `pipeline.py` |
| 16 | Outputs: summary CSVs, runs.jsonl, status.json, monthly dataset asset, HF upload (skip without token), dbt docs | todo | `publish.py` |
| 17 | Dashboard: static site in `site/`, Playwright screenshots at 360/768/1440 | todo | `src/jobpipe/site/` |
| 18 | Daily workflow (41 7 * * *), timeouts, concurrency, alert issue on failure/held | todo | `.github/workflows/daily.yml` |
| 19 | CI: ruff, mypy, pytest, dbt build on fixtures, gitleaks, pip-audit, 50 MB file guard | todo | `.github/workflows/ci.yml` |
| 20 | First real runs; fix incidents; record in docs/incidents.md | todo | |
| 21 | README + animated SVGs from real run data (waits for the owner's README rules) | todo | notes in `docs/readme-plan.md` |
