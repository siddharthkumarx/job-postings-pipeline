# Architecture

## One-paragraph summary

Once a day a GitHub Actions workflow reads every tracked company's public job
board (Greenhouse, Lever, Ashby: one GET per board), turns each posting into one
validated Pydantic record without free text or personal data, and writes a
**bronze** Parquet snapshot for that run date. The snapshot and the per-board
fetch log are uploaded as GitHub Release assets: they are the source of truth.
**dbt-duckdb** then builds **silver** (deduped, parsed postings), **history**
(first/last seen, closed, SCD2) and **gold** marts in a DuckDB file. Quality
gates (dbt tests, freshness, row-count and null-rate guards, enforced contracts)
decide whether the run is **published** or **held**. Published runs refresh the
public outputs: summary CSVs, `runs.jsonl`, `status.json` (shields.io badges),
the monthly Parquet dataset (Release asset and Hugging Face), dbt docs and the
static dashboard in `site/`.

```
seeds/boards.csv ──► ingest (httpx, polite) ──► bronze Parquet  ──► Release assets  (truth)
                        │  descriptions read in memory only:            bronze-YYYY-MM
                        │  salary / remote / seniority hints + sha256
                        ▼
ECB reference rates ─► bronze fx Parquet
                        ▼
                 dbt-duckdb (warehouse.duckdb)
   staging (silver) → intermediate (history, SCD2) → marts (gold, contracts)
                        ▼
            guards: dbt tests, freshness, row count, null rate
              │ pass                              │ fail
              ▼                                   ▼
   publish: public/*.csv, runs.jsonl,       hold: keep last good outputs,
   status.json, monthly dataset,            runs.jsonl status=held,
   dbt docs, site/                          alert issue opened
```

## Layers

| Layer | Where | Grain | Built by |
|---|---|---|---|
| bronze postings | `data/bronze/postings/run_date=D/part-0.parquet`; Release `bronze-YYYY-MM`, asset `postings_D.parquet` | one row per posting per run | `jobpipe.ingest` |
| bronze board log | `data/bronze/board_runs/run_date=D/part-0.parquet`; asset `board_runs_D.parquet` | one row per board per run (status, jobs, latency) | `jobpipe.ingest` |
| bronze manifest | `data/bronze/manifests/run_date=D.json`; asset `manifest_D.json` | counts, HTTP stats, duration | `jobpipe.ingest` |
| bronze fx | `data/bronze/fx/ecb_eurofxref.parquet`; asset `fx_D.parquet` | one row per currency per ECB business day | `jobpipe.fx` |
| silver | `dbt/models/staging/` | posting × run date, parsed | dbt |
| history | `dbt/models/intermediate/` | posting lifecycle; SCD2 versions | dbt |
| gold | `dbt/models/marts/` | facts, dims, weekly aggregates | dbt (contracts enforced on public tables) |

### Bronze record (Pydantic `jobpipe.models.Posting`)

API fields minus free text and personal fields, plus derived fields extracted in
memory: `provider, board, posting_id, requisition_id, title, department, team,
location_raw, locations_all, workplace_type_raw, employment_type, country_hint,
is_listed, published_at, updated_at, job_url, api_salary_min, api_salary_max,
api_salary_currency, api_salary_period, desc_salary_min, desc_salary_max,
desc_salary_currency, desc_salary_period, desc_remote_hint, desc_seniority_hint,
description_sha256, description_chars, run_date, fetched_at, schema_version`.

Never stored: description text/HTML, Greenhouse `metadata` custom fields,
Greenhouse questions, Lever `lists`/`additional`, Ashby `descriptionHtml/Plain`,
any name, email or phone number.

## Daily run (`jobpipe run --date D`)

1. **restore state**: download `warehouse.duckdb.gz` and `state/state.json` from the `state` Release. If absent or unreadable, `jobpipe rebuild` downloads every bronze asset and replays it.
2. **ingest**: fetch all boards with the polite client (`docs/decisions.md` D-002), write bronze for D, upload bronze assets (replacing any earlier upload for D, so the run is idempotent).
3. **fx**: fetch ECB reference rates, write the bronze fx file.
4. **dbt build**: `dbt build --vars '{run_from: D, run_to: D}'`. Incremental models delete and re-insert the run dates in range; history and marts recompute from silver.
5. **guards**: row-count change vs the last good run, null rates on key columns, share of boards fetched OK. A failure marks the run **held**.
6. **publish** (only if not held): export public tables, summary CSVs, `status.json`, monthly dataset asset, optional HF upload, dbt docs, dashboard.
7. **persist**: append to `public/runs.jsonl` (always), commit `public/`, upload the warehouse snapshot (only when published, so state is always the last good build).
8. **alert**: a failed or held run opens or updates a GitHub issue labelled `pipeline-alert`.

`jobpipe backfill --from A --to B` re-processes stored bronze snapshots for that
date range: it downloads them, re-runs dbt for the range and republishes. The
APIs show only currently open postings, so days that were never fetched cannot
be backfilled; they are counted as missed runs.

## State

The source of truth is bronze in GitHub Release assets (`docs/decisions.md`
D-007). The warehouse file is a cache of the last good build and can always be
rebuilt from bronze. Git holds only code, seeds, small public outputs (<1 MB each)
and check results; every file in git stays under 50 MB (CI enforces it).

## Repository layout

```
src/jobpipe/            Python package (ingest, http, providers, geo, extract, fx, state, guards, publish, site)
dbt/                    dbt project (profiles.yml in repo, paths from env vars)
seeds/boards.csv        tracked boards (from recon)
public/                 small published outputs committed by the daily run
checks/                 live-check requests and results (Actions-only network access)
tests/                  pytest, golden fixtures in tests/fixtures/<provider>/
site/                   built dashboard (gitignored; built in CI)
docs/                   decisions, sources, contracts, progress, incidents
.github/workflows/      ci.yml, checks.yml, daily.yml
```

## dbt models

| Layer (schema) | Model | Materialisation | Notes |
|---|---|---|---|
| silver | `stg_postings` | incremental, delete+insert on `run_date` | dedupe, cleaning, salary chosen api-first |
| silver | `stg_board_runs` | incremental, delete+insert on `run_date` | fetch outcome per board |
| silver | `stg_fx_rates`, `stg_tracked_boards` | view | ECB rates; seeds/boards.csv |
| history | `int_title_labels` | table | taxonomy seeds → role family, title seniority |
| history | `int_locations` | table (dbt Python model) | `jobpipe.geo.parse_location` |
| history | `int_postings_daily` | incremental | enriched posting × run date, `attr_hash` |
| history | `int_run_calendar` | table | run dates with ≥ 1 OK board |
| history | `int_posting_lifecycle` | table | first/last seen, closed, reopened, days open |
| history | `int_posting_versions` | table | SCD2 |
| gold | `fct_job_postings`, `dim_company`, `mart_*` | table, contract enforced | public tables (`docs/data-contracts.md`) |

Seeds (schema `ref`): `role_taxonomy`, `seniority_rules`. Custom generic tests:
`column_between`, `unique_combination`, `expression_is_true` (`dbt/tests/generic/`).

`dbt/models/marts/_marts.yml` is generated from `docs/data-contracts.md` by
`scripts/gen_marts_yml.py`; `tests/test_contracts_doc.py` fails when they drift.

## Code map

| Module | Job |
|---|---|
| `jobpipe.http` | polite async client (per-host limits, retries, Retry-After, blocks) |
| `jobpipe.providers.*` | one adapter per provider: URL, params, allowlisted fields |
| `jobpipe.extract` | in-memory description analysis (salary, remote, seniority, sha256) |
| `jobpipe.models` | Pydantic `Posting` / `BoardRun`, Parquet schema |
| `jobpipe.ingest` | fetch all boards → bronze Parquet + manifest |
| `jobpipe.fx` | ECB reference rates → bronze fx |
| `jobpipe.geo` | location → country / state / city |
| `jobpipe.state` | GitHub Release assets: bronze, warehouse snapshot |
| `jobpipe.warehouse` | dbt runner wrapper |
| `jobpipe.guards` | run stats + hold rules |
| `jobpipe.publish` | exports, summary CSVs, runs.jsonl, status.json, badges, HF |
| `jobpipe.pipeline` | daily / backfill / rebuild / release-hold orchestration |
| `jobpipe.site` | static dashboard |
| `jobpipe.recon` | one-off board discovery (harvest, verify, select) |
| `jobpipe.checks` | live-check runner for Actions |
| `jobpipe.fixtures` | synthetic bronze for offline dbt builds |
