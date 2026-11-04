# docs/maintainers.md: job-postings-pipeline

Read this first, then `docs/build-progress.md` ("Continue here" is at the bottom of this file).

## Goal

A daily hiring-data pipeline for about 1,500 US tech companies, built from their
public job boards (Greenhouse, Lever, Ashby) and loaded into a DuckDB + dbt
warehouse, with a public dashboard and dataset. It becomes the public portfolio
repo `job-postings-pipeline` of Siddharth Kumar (web scraping and data
engineering freelancer, siddharthkumar.com). It must show production-grade data
engineering: layers, incremental loads, history, tests and data contracts.
**Every number shown anywhere must come from real runs.**

## Hard rules

### Git
- Commit as `Siddharth Kumar <273157498+siddharthkumarx@users.noreply.github.com>` (repo-local `git config`).
- Commit messages carry no trailers except `Signed-off-by`, and no "Generated with" footer. `.githooks/commit-msg` removes them (`git config core.hooksPath .githooks`; rule in `scripts/commit_guard.py`), and the CI job `commit-messages` fails on any commit that has one.
- Never open a PR. Work on the designated branch only. Small, meaningful commits.
- Every file in git stays under 50 MB (CI guard). Bulk data lives in GitHub Release assets.

### Live checks
- The dev sandbox does **not** call the job boards. Every live call runs on GitHub Actions: change `checks/request.yml` (new `id`, a whitelisted `command`, `params`), push, wait for the `checks` workflow to commit `checks/results/<id>/`, then `git pull`.

### Sources
- Official public job-board APIs only: Greenhouse Job Board API, Lever Postings API, Ashby Posting API. Docs and terms are recorded in `docs/decisions.md` D-001.
- Polite: per-host concurrency cap + delay (Lever ≤ 1 request/s per its robots.txt crawl-delay); retries only on 429/5xx/network errors; honour Retry-After; a block (403, 429 after retries, Retry-After above the cap) stops that host for the run.

### Privacy and copyright
- Never store or publish full job-description text, or recruiter / hiring-manager names, emails or phone numbers.
- Descriptions may be read **in memory during the run only** to extract structured fields (salary, remote/hybrid, seniority hints). Keep `description_sha256` for change detection.
- Greenhouse `metadata` custom fields are dropped (they can hold names).
- Public outputs carry only metadata and derived fields: title, company, department, location, remote type, salary min/max/currency/period, dates, job URL.

### Selection rules (approved by the owner)
- Companies only: drop staffing/recruiting agencies, job aggregators, test/demo boards and boards with 0 US roles.
- One board per company: if a company is on two providers, keep the one with more open jobs and note it.
- Keep ≥ 1,000 companies (target ~1,500) with all three providers represented; record counts per provider.
- One full daily run must finish in under 45 minutes with Lever at 1 request/s (estimate in `docs/decisions.md` D-009).
- `docs/sources.md` lists the final boards, the seed sources and every dropped board with its reason.

### Dashboard look
Background `#0B1416`; panels `#0F1C1E` with border `#1D3331`; main text `#EAF2F0`; body text `#C9D8D5`; quiet text `#7E9996`; teal `#2FBFAE` = good / growth; amber `#E9A93C` = look here / drop / change. Fonts: Instrument Sans (headings, text) and IBM Plex Mono (data, tables), self-hosted. No external scripts; text contrast ≥ 4.5:1; works from 360 to 1920 px; respects reduced motion; aim for Lighthouse 100. GitHub Pages turns on only after the public publish. Until then, check with Playwright screenshots at 360, 768 and 1440 px.

### README and visuals (owner's rules, 2026-11-04)
- `README.md` is generated: edit `templates/README.md.j2` (and `templates/readme.yml` for the public URLs), never README.md itself. Every daily run re-renders it with `jobpipe readme`, together with `docs/dataset-card.md` and `assets/*.svg`.
- Readers are clients first (recruiters, HR-tech teams, analysts, data hiring managers), engineers second. Use plain words, short sentences and no jargon above the "For engineers" section. Keep the section order fixed (the test in `tests/test_readme.py` enforces it).
- Every number, row and log line shown comes from real runs. Growing numbers come from `status.json` badges or regenerated sections. A drawn illustration with made-up data must carry a small "EXAMPLE" label.
- Visuals: CSS-only animation, 6–10 s loops, the final frame holds and is the still, reduced motion shows the final frame. Fonts are embedded subsets. At most 3 lines of text, text ≥ 22 px in a 1000-px viewBox, colours from the dashboard palette. Render them with Playwright at 390 and 1280 px after changes.
- No HTML comments, notes or placeholders in the rendered README (`readme.check_rendered`).

## Stack
Python 3.12 with uv, httpx, pydantic, PyYAML, duckdb, dbt-core + dbt-duckdb, pyarrow. Versions and licenses are in `docs/decisions.md` D-005.

## Commands

```bash
uv sync                                   # install (Python 3.12)
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
uv run jobpipe checks checks/request.yml  # what the checks workflow runs (Actions only)
uv run jobpipe recon-select --verify checks/results/<verify-id>/verify.csv --harvest checks/results/<harvest-id>/summary.json
uv run jobpipe run --date 2026-11-04      # daily run (Actions only: needs network + GITHUB_TOKEN)
uv run jobpipe backfill --from 2026-11-04 --to 2026-11-10
uv run jobpipe rebuild                    # rebuild the warehouse from all bronze assets
uv run jobpipe fixtures-build             # run dbt on golden fixtures (offline, used by CI)
uv run jobpipe site --out site            # build the dashboard from the warehouse/public outputs
uv run jobpipe readme                     # re-render README.md, docs/dataset-card.md, assets/*.svg
node scripts/render_media.js              # assets/social-preview.png + media/linkedin-hero.mp4 (playwright + ffmpeg)
python3 scripts/check_links.py            # internal Markdown links
cd dbt && uv run dbt build --profiles-dir . # needs JOBPIPE_DATA / JOBPIPE_DUCKDB env vars
```

## Where things are
- `docs/architecture.md`: layers, daily run, state, layout.
- `docs/decisions.md`: every decision with its reason (sources, terms, politeness, state, taxonomy, FX, run-time estimate).
- `docs/data-contracts.md`: public tables, columns, types, guarantees.
- `docs/sources.md`: tracked boards, seed sources, funnel, dropped boards.
- `docs/incidents.md`: what broke and how it was fixed.
- `docs/build-progress.md`: numbered build items and status.

## Continue here

Status (2026-11-04): all build items 1–21 are done (`docs/build-progress.md`). The
pipeline runs daily at 07:41 UTC on the working branch (the repo's default branch)
and re-renders the README and visuals each time.

Next:
1. Each morning, check `public/runs.jsonl` / `public/status.json` and any open
   `pipeline-alert` issue. Fix problems and log them in `docs/incidents.md`, filling in
   both "In plain words" lines, because the README shows them. After a week of runs,
   tune the guard thresholds (D-012).
2. To publish, follow `docs/publish-checklist.md`: a fresh public repo
   `job-postings-pipeline` with a clean `main` (not a rename), without `docs/private/`, with
   this file moved to `docs/maintainers.md`, the `templates/readme.yml` URLs checked, the
   release assets copied, and `docs/repo-settings.md` applied.
3. Re-render `media/linkedin-hero.mp4` and `assets/social-preview.png` with
   `node scripts/render_media.js` whenever you post them, so they show current numbers.
