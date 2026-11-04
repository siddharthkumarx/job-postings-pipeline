# Repository settings (paste when the repo goes public)

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
- **Default branch:** `main`. The badge URLs in `templates/readme.yml` read `public/badges/*.json` from `main`; change `branch` there if the default branch has another name.
- **Releases:** the `dataset-YYYY-MM` release is marked "latest" by every run, so the README's "Download the data" link always points at the current month.
- **Remove before publishing:** `docs/private/`, plus `checks/results/` if you prefer a smaller repo (they document how the recon was done, so keeping them is fine).
