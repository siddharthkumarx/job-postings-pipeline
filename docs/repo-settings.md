# Repository settings (paste into the public repo)

The public repo is created fresh, not renamed; follow `docs/publish-checklist.md` first.

## About → Description (under 350 characters)

Daily web scraping and data engineering pipeline: every open job at 1,500 US tech companies, collected from public Greenhouse, Lever and Ashby job boards, tested with dbt and published as a free dataset (CSV, Parquet) and dashboard. Python, DuckDB, dbt, GitHub Actions.

(269 characters)

## About → Website

https://siddharthkumar.com/job-postings-pipeline/

## About → Topics (15)

```
web-scraping
data-engineering
job-postings
hiring-data
labor-market
dbt
duckdb
python
etl-pipeline
data-pipeline
github-actions
open-data
salary-data
greenhouse
data-quality
```

## Social preview

Settings → General → Social preview → upload `assets/social-preview.png` (1280×640).

## Other settings

- **Pages:** Settings → Pages → Source: GitHub Actions; custom domain `siddharthkumar.com` is served from the owner's site, so the dashboard lives at `/job-postings-pipeline/`. Then set the repository variable `PAGES_ENABLED=true` (Settings → Secrets and variables → Actions → Variables).
- **Secret `HF_TOKEN`:** a Hugging Face write token, for the dataset upload (the run skips it cleanly when absent).
- **Default branch:** `main`. The badge URLs read `public/badges/*.json` from `main` (set in `templates/readme.yml`).
- **Releases:** the `dataset-YYYY-MM` release is marked "latest" by every run, so the README's "Download the data" link always points at the current month.
- **Before publishing:** follow `docs/publish-checklist.md` (drop `docs/private/`, rename `docs/maintainers.md` to `docs/maintainers.md`, check `templates/readme.yml`).
