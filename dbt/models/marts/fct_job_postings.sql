{#
  One row per posting ever seen: current attributes (from the last listing), lifecycle,
  SCD2 version count and salary converted to annual USD at the ECB rate on first_seen.
  Salaries whose annual USD value falls outside 10k-2M are treated as extraction noise
  and dropped (all salary columns null).
#}
with lc as (
    select * from {{ ref('int_posting_lifecycle') }}
),

cur as (
    select d.*
    from {{ ref('int_postings_daily') }} as d
    inner join lc on lc.posting_key = d.posting_key and lc.last_seen = d.run_date
),

versions as (
    select posting_key, count(*) as version_count
    from {{ ref('int_posting_versions') }}
    group by 1
),

fx as (
    select * from {{ ref('stg_fx_rates') }}
),

priced as (
    select
        cur.*,
        lc.first_seen,
        fx.rate_date as fx_rate_date,
        cur.salary_min_annual * fx.usd_per_unit as min_usd,
        cur.salary_max_annual * fx.usd_per_unit as max_usd
    from cur
    inner join lc on lc.posting_key = cur.posting_key
    asof left join fx
        on fx.currency = cur.salary_currency and lc.first_seen >= fx.rate_date
),

checked as (
    select
        *,
        coalesce(min_usd between 10000 and 2000000 and max_usd between 10000 and 2000000, false)
            as salary_ok
    from priced
)

select
    c.posting_key,
    c.provider,
    c.board,
    c.company_id,
    coalesce(tb.company_name, c.board) as company_name,
    c.posting_id,
    c.title,
    c.role_family,
    c.seniority,
    c.seniority_source,
    c.department,
    c.location_raw,
    c.country_code,
    c.state_code,
    c.city,
    c.remote_type,
    c.employment_type,
    case when c.salary_ok then c.salary_min end as salary_min,
    case when c.salary_ok then c.salary_max end as salary_max,
    case when c.salary_ok then c.salary_currency end as salary_currency,
    case when c.salary_ok then c.salary_period end as salary_period,
    case when c.salary_ok then c.salary_min_annual end as salary_min_annual,
    case when c.salary_ok then c.salary_max_annual end as salary_max_annual,
    case when c.salary_ok then round(c.min_usd, 0) end as salary_min_usd_annual,
    case when c.salary_ok then round(c.max_usd, 0) end as salary_max_usd_annual,
    case when c.salary_ok then c.salary_source end as salary_source,
    case when c.salary_ok then c.fx_rate_date end as fx_rate_date,
    c.job_url,
    c.published_at,
    lc.first_seen,
    lc.last_seen,
    lc.closed_on,
    lc.is_open,
    cast(lc.days_open as integer) as days_open,
    lc.left_censored,
    cast(coalesce(v.version_count, 1) as integer) as version_count,
    c.taxonomy_version
from checked as c
inner join lc on lc.posting_key = c.posting_key
left join versions as v on v.posting_key = c.posting_key
left join {{ ref('stg_tracked_boards') }} as tb on tb.company_id = c.company_id
