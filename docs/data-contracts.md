# Data contracts

The public tables are what the dataset, the summary CSVs and the dashboard read.
Each one is a dbt model with `contract: {enforced: true}`: dbt refuses to build
it if a column's name, order or type drifts from the YAML in
`dbt/models/marts/_marts.yml`. That YAML and this page must agree. A unit test
(`tests/test_contracts_doc.py`) parses both and fails if they diverge.

## Guarantees (all public tables)

- **Content**: metadata and derived fields only. No description text, no names, emails or phone numbers of people.
- **Freshness**: rebuilt by every published daily run (07:41 UTC schedule). `status.json` → `last_run` says when.
- **Holds**: if a run fails a quality gate, the previous published version stays in place (`runs.jsonl` records `held`).
- **Keys**: the primary key listed for each table is unique and not null (dbt tests).
- **Types**: DuckDB types as listed (TIMESTAMPTZ = timestamp with time zone, UTC). Dates are UTC calendar dates; money is in the stated currency, annualised as described.
- **Versioning**: adding a nullable column is non-breaking; it is documented here and released. Removing or renaming a column, changing its type or changing its meaning is breaking: it ships as a new dbt model version (`v2`), and the old version is kept for at least 60 days with a deprecation date.
- **Taxonomy**: `role_family` and `seniority` follow `taxonomy_version` (see `docs/decisions.md` D-006). A taxonomy change re-labels all history at the next rebuild and is announced in `docs/decisions.md`.

## fct_job_postings

One row per posting ever seen. Primary key `posting_key`.

| Column | Type | Meaning |
|---|---|---|
| posting_key | VARCHAR | md5 of `provider|board|posting_id` |
| provider | VARCHAR | `greenhouse`, `lever`, `ashby` |
| board | VARCHAR | board name at the provider |
| company_id | VARCHAR | FK → dim_company.company_id |
| company_name | VARCHAR | display name |
| posting_id | VARCHAR | provider's posting id |
| title | VARCHAR | current title |
| role_family | VARCHAR | taxonomy family (see accepted values below) |
| seniority | VARCHAR | `intern`, `junior`, `mid`, `senior`, `staff_principal`, `manager`, `director`, `vp_exec` |
| seniority_source | VARCHAR | `title`, `description`, `default` |
| department | VARCHAR | department or team as published |
| location_raw | VARCHAR | primary location string as published |
| country_code | VARCHAR | ISO 3166-1 alpha-2, `XX` multi-country region, null unknown |
| state_code | VARCHAR | US state/territory postal code (US only) |
| city | VARCHAR | city when identifiable |
| remote_type | VARCHAR | `remote`, `hybrid`, `onsite`, `unknown` |
| employment_type | VARCHAR | `full_time`, `part_time`, `contract`, `intern`, `temporary`, `unknown` |
| salary_min | DOUBLE | as published, in `salary_currency` per `salary_period` |
| salary_max | DOUBLE | as published |
| salary_currency | VARCHAR | ISO 4217 |
| salary_period | VARCHAR | `year`, `month`, `week`, `day`, `hour` |
| salary_min_annual | DOUBLE | annualised (hour × 2080, day × 260, week × 52, month × 12) |
| salary_max_annual | DOUBLE | annualised |
| salary_min_usd_annual | DOUBLE | annualised, in USD at the ECB rate on `fx_rate_date` |
| salary_max_usd_annual | DOUBLE | as above |
| salary_source | VARCHAR | `api`, `description`, null |
| fx_rate_date | DATE | ECB business day used for USD conversion |
| job_url | VARCHAR | public posting URL at the provider |
| published_at | TIMESTAMPTZ | provider's publish/update timestamp when given |
| first_seen | DATE | first run date listed |
| last_seen | DATE | last run date listed |
| closed_on | DATE | first missing run date once closed (2 consecutive successful-fetch absences), else null |
| is_open | BOOLEAN | listed on the latest run |
| days_open | INTEGER | see D-011 |
| left_censored | BOOLEAN | already open on the first run of the pipeline |
| version_count | INTEGER | number of SCD2 versions (title/location/salary changes + 1) |
| taxonomy_version | VARCHAR | version of role/seniority rules applied |

Accepted `role_family` values: `software_engineer`, `data_engineer`, `analytics_engineer`, `data_analyst`, `data_scientist`, `ml_engineer`, `devops_sre`, `security`, `product_manager`, `design`, `qa_test`, `it_support`, `hardware_engineer`, `solutions_engineer`, `engineering_manager`, `sales`, `marketing`, `customer_success`, `operations`, `finance`, `people_hr`, `legal`, `other`.

## dim_company

One row per tracked company. Primary key `company_id`.

| Column | Type | Meaning |
|---|---|---|
| company_id | VARCHAR | md5 of `provider|board` |
| company_name | VARCHAR | display name |
| provider | VARCHAR | ATS provider of the tracked board |
| board | VARCHAR | board name |
| board_url | VARCHAR | public API URL of the board |
| first_tracked | DATE | first run date the board was fetched |
| last_fetch_status | VARCHAR | `ok`, `not_found`, `error`, `blocked` on the latest run |
| open_postings | INTEGER | open postings on the latest run |
| open_us_postings | INTEGER | open postings with country_code = 'US' |
| postings_seen | INTEGER | all postings ever seen |

## mart_weekly_open_roles

Primary key (`week_start`, `company_id`, `role_family`, `country_code`, `state_code`), with nulls coalesced to `''` in the key.

| Column | Type | Meaning |
|---|---|---|
| week_start | DATE | Monday of the ISO week |
| company_id | VARCHAR | FK → dim_company |
| role_family | VARCHAR | taxonomy family |
| country_code | VARCHAR | `''` when unknown |
| state_code | VARCHAR | `''` when not US / unknown |
| open_roles | INTEGER | postings open on the last run of the week |
| new_roles | INTEGER | postings with first_seen in the week |
| closed_roles | INTEGER | postings with closed_on in the week |

## mart_days_open_bands

Primary key (`role_family`, `band`). Only closed, non-left-censored postings count.

| Column | Type | Meaning |
|---|---|---|
| role_family | VARCHAR | taxonomy family, plus `all` |
| band | VARCHAR | `0-7`, `8-14`, `15-30`, `31-60`, `61-90`, `91+` |
| band_order | INTEGER | 1..6 |
| closed_postings | INTEGER | count in band |
| share | DOUBLE | share within role_family |
| median_days_open | DOUBLE | median for the role_family (repeated per band) |

## mart_salary_bands

Primary key (`role_family`, `seniority`). US postings with a salary, annual USD midpoint.

| Column | Type | Meaning |
|---|---|---|
| role_family | VARCHAR | taxonomy family, plus `all` |
| seniority | VARCHAR | level, plus `all` |
| postings_with_salary | INTEGER | n |
| p25_usd | DOUBLE | 25th percentile of the annual USD midpoint |
| median_usd | DOUBLE | median |
| p75_usd | DOUBLE | 75th percentile |
| share_with_salary | DOUBLE | share of US postings in the group that publish a salary |

## mart_hiring_velocity

Primary key (`week_start`, `company_id`).

| Column | Type | Meaning |
|---|---|---|
| week_start | DATE | ISO week Monday |
| company_id | VARCHAR | FK → dim_company |
| new_postings | INTEGER | first_seen in week |
| closed_postings | INTEGER | closed_on in week |
| net_change | INTEGER | new − closed |
| open_at_week_end | INTEGER | open on the last run of the week |
| velocity | DOUBLE | new_postings / nullif(open_at_week_end, 0) |

## mart_data_roles

Posting-level subset of fct_job_postings where `role_family` ∈ (`data_engineer`, `analytics_engineer`, `data_analyst`, `ml_engineer`). Same columns as fct_job_postings (contracted identically). Primary key `posting_key`.
