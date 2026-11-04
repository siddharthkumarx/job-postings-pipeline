# Build progress

Update this file after every item: set the status, add the commit and a one-line note.
Status: `todo` · `doing` · `done` · `blocked`.

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Repo skeleton: uv project, ruff/mypy/pytest, commit-msg hook, CI commit-message job | done | `.githooks/commit-msg`, `scripts/check_commit_messages.py` |
| 2 | Polite HTTP client (per-host cap + delay, retry 429/5xx/network, Retry-After, block stops host) | done | `src/jobpipe/http.py`, `tests/test_http.py` |
| 3 | Live-check workflow (`checks/request.yml` → `checks/results/<id>/`) | done | `.github/workflows/checks.yml`, `src/jobpipe/checks.py` |
| 4 | Recon: harvest seeds (Common Crawl index, YC directory), verify via APIs, select boards, `docs/sources.md` | done | 9,904 candidates → 1,500 kept (GH 779, Ashby 669, Lever 52); `seeds/boards.csv` |
| 5 | Step-2 docs: docs/maintainers.md, architecture, build-progress, decisions, data-contracts, incidents | done | kept in sync as items land |
| 6 | Golden fixtures per provider (captured by a live check, sanitised) | done | 5 boards from recon-verify-001; descriptions replaced with marked synthetic text |
| 7 | Bronze model + adapters: Pydantic `Posting`, one adapter per provider, description extraction in memory | done | allowlisted fields only; `tests/test_extract.py`, `tests/test_ingest.py` |
| 8 | Ingest: run all boards → bronze Parquet (postings + board log), run manifest | done | atomic writes; privacy asserted in tests |
| 9 | FX: ECB reference rates → bronze fx | done | `fx.py`, `tests/test_fx.py` |
| 10 | State: GitHub Release assets sync (bronze, warehouse snapshot, state.json), rebuild from bronze | done | upload-then-rename swap; `tests/test_state.py` |
| 11 | dbt project + staging (silver): dedupe, role taxonomy, seniority, location, salary + USD | done | taxonomy 2026-11-03; location via dbt Python model |
| 12 | History: first/last seen, closed (2 missed fetches), days open, SCD2 (title, location, salary) | done | verified on synthetic fixtures (close, reopen, failed fetch, SCD2) |
| 13 | Marts (gold): fct_job_postings, dim_company, weekly open roles, days-open + salary bands, velocity, data roles | done | contracts generated from docs/data-contracts.md |
| 14 | Quality: dbt tests, source freshness, guards (row count, null rate), contracts, hold logic | done | 91 dbt tests; guards in `guards.py`; thresholds to tune on real runs |
| 15 | Orchestration: `jobpipe run`, `backfill --from --to`, `rebuild`; idempotency | done | `tests/test_pipeline.py` runs 6 days + rebuild against a fake GitHub API |
| 16 | Outputs: summary CSVs, runs.jsonl, status.json, monthly dataset asset, HF upload (skip without token), dbt docs | done | badges in `public/badges/*.json` (shields endpoint schema) |
| 17 | Dashboard: static site in `site/`, Playwright screenshots at 360/768/1440 | done | real data, `docs/screenshots/` (from check site-screenshots-003); 0 px horizontal overflow at all widths |
| 18 | Daily workflow (41 7 * * *), timeouts, concurrency, alert issue on failure/held | done | Pages job gated by repo variable `PAGES_ENABLED` |
| 19 | CI: ruff, mypy, pytest, dbt build on fixtures, gitleaks, pip-audit, 50 MB file guard | done | green since run 5; golden fixtures added |
| 20 | First real runs; fix incidents; record in docs/incidents.md | done | 2026-11-04: failed → held → published (9.7 min), re-run from snapshot published (9.4 min); 2 incidents fixed |
| 21 | README + animated SVGs from real run data (waits for the owner's README rules) | todo | notes in `docs/readme-plan.md` |
