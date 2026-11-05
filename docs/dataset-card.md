---
license: cc-by-4.0
pretty_name: US tech job postings (daily)
language:
- en
tags:
- jobs
- job-postings
- hiring
- labor-market
- salaries
- data-engineering
task_categories:
- tabular-classification
- time-series-forecasting
size_categories:
- 10K<n<100K
configs:
- config_name: default
  data_files: "data/job_postings_*.parquet"
---

# US tech job postings (daily)

Open jobs at 1,500 US tech companies, collected every day from their public Greenhouse, Lever and Ashby job boards by the open-source pipeline [siddharthkumarx/job-postings-pipeline](https://github.com/siddharthkumarx/job-postings-pipeline). The latest run, on 2026-11-05, listed 65,483 open postings.

## Dataset summary

- **One row per job posting ever seen.** Each row has the current attributes of the posting (title, role family, seniority, location, remote type, salary range), its lifecycle (first seen, last seen, closed on, days open) and a link to the original posting.
- **Files:** one Parquet file per month, `data/job_postings_YYYY-MM.parquet`, containing every posting seen during that month. It is refreshed every day of the month.
- **Coverage:** 779 companies on Greenhouse, 669 on Ashby and 52 on Lever. How they were chosen is in [docs/sources.md](https://github.com/siddharthkumarx/job-postings-pipeline/blob/main/docs/sources.md).

## Fields

| Field | Type | Meaning |
|---|---|---|
| `posting_key` | text | Unique ID of the job posting in this dataset |
| `provider` | text | Job-board software the company uses: Greenhouse, Lever or Ashby |
| `board` | text | The company's board name on that job board |
| `company_id` | text | Unique ID of the company in this dataset |
| `company_name` | text | Company name |
| `posting_id` | text | The job board's own ID for the posting |
| `title` | text | Job title as the company wrote it |
| `role_family` | text | Role type worked out from the title (e.g. data engineer) |
| `seniority` | text | Level worked out from the title (intern to VP) |
| `seniority_source` | text | Where the level came from: the title, the job ad text, or a default |
| `department` | text | Department or team as published |
| `location_raw` | text | Main location as the company wrote it |
| `country_code` | text | Country code (US, GB …); empty if unknown |
| `state_code` | text | US state code, for US jobs |
| `city` | text | City, when it can be read from the location |
| `remote_type` | text | Remote, hybrid, on-site, or not stated |
| `employment_type` | text | Full-time, part-time, contract, internship, temporary, or not stated |
| `salary_min` | number | Lowest salary as published, in its own currency and period |
| `salary_max` | number | Highest salary as published |
| `salary_currency` | text | Currency of the published salary |
| `salary_period` | text | Whether the published salary is per year, month, week, day or hour |
| `salary_min_annual` | number | Lowest salary converted to a yearly amount |
| `salary_max_annual` | number | Highest salary converted to a yearly amount |
| `salary_min_usd_annual` | number | Lowest yearly salary in US dollars |
| `salary_max_usd_annual` | number | Highest yearly salary in US dollars |
| `salary_source` | text | Where the salary came from: the job board's salary field or the ad text |
| `fx_rate_date` | date | Date of the official exchange rate used for the dollar conversion |
| `job_url` | text | Link to the original posting |
| `published_at` | date and time (UTC) | When the company published or last updated the posting |
| `first_seen` | date | First day the job was seen |
| `last_seen` | date | Last day the job was seen |
| `closed_on` | date | Day the job was counted as closed (missing two days in a row) |
| `is_open` | yes / no | Whether the job was open in the latest run |
| `days_open` | whole number | Days the job has been open so far, or was open in total |
| `left_censored` | yes / no | Yes if the job was already open on the first day it was tracked |
| `version_count` | whole number | How many times the title, location or salary changed, plus one |
| `taxonomy_version` | text | Version of the rules used for role type and level |

The full contract (types, keys, guarantees, versioning policy) is in [docs/data-contracts.md](https://github.com/siddharthkumarx/job-postings-pipeline/blob/main/docs/data-contracts.md).

## How the data is made

1. Each company's public job board is read once a day through the official job-board API (Greenhouse Job Board API, Lever Postings API, Ashby Posting API), with per-host rate limits.
2. Job descriptions are read in memory only, to extract salary and remote hints, and are never stored.
3. dbt models deduplicate, classify titles (versioned taxonomy), parse locations, annualise salaries and convert them to USD at the ECB reference rate, and track each posting's history.
4. Quality gates (data tests, row-count and null-rate guards, a single-posting spot check) decide whether a day is published. A doubtful day is held back instead.

## Known limitations

- Only companies that use Greenhouse, Lever or Ashby are covered, and the 1,500 were chosen by a documented rule (mostly US roles, mostly tech titles).
- Salary is present only when the company publishes it (in the posting data or the description).
- Days open are known exactly only for postings first seen after the pipeline started; earlier postings are flagged `left_censored`.
- Role family and seniority come from title rules and can be wrong for unusual titles.

## Personal data and opt-out

The dataset contains no personal data: no recruiter or hiring-manager names, emails or phone numbers, and no description text. Companies can ask for their postings to be removed by emailing hello@siddharthkumar.com; removal happens within 24 hours.

## License and citation

CC BY 4.0 for the compiled dataset. Each posting belongs to the company that published it and is linked at its source. Please cite with the metadata in [CITATION.cff](https://github.com/siddharthkumarx/job-postings-pipeline/blob/main/CITATION.cff):

> Siddharth Kumar. *US tech job postings (daily)*. https://github.com/siddharthkumarx/job-postings-pipeline

Maintained by Siddharth Kumar · https://siddharthkumar.com
