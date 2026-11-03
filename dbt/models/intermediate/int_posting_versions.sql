{#
  SCD2 over title, location and salary (docs/decisions.md D-011). A version starts on
  the first run date where attr_hash differs from the previous listing; valid_to is
  exclusive (the next version's valid_from); is_current marks the latest version.
#}
with d as (
    select
        posting_key, run_date, title, location_raw, salary_min, salary_max,
        salary_currency, salary_period, attr_hash,
        lag(attr_hash) over (partition by posting_key order by run_date) as prev_hash
    from {{ ref('int_postings_daily') }}
),

starts as (
    select * from d where prev_hash is null or prev_hash <> attr_hash
)

select
    md5(posting_key || '|' || cast(run_date as varchar)) as version_key,
    posting_key,
    row_number() over (partition by posting_key order by run_date) as version_number,
    run_date as valid_from,
    lead(run_date) over (partition by posting_key order by run_date) as valid_to,
    lead(run_date) over (partition by posting_key order by run_date) is null as is_current,
    title,
    location_raw,
    salary_min,
    salary_max,
    salary_currency,
    salary_period,
    attr_hash
from starts
