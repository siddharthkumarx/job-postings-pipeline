-- Annual USD salary bands (midpoint) for US postings seen in the last 365 days.
with us as (
    select
        role_family,
        seniority,
        (salary_min_usd_annual + salary_max_usd_annual) / 2 as mid_usd
    from {{ ref('fct_job_postings') }}
    where country_code = 'US'
        and last_seen >= (select max(last_seen) from {{ ref('fct_job_postings') }}) - interval 365 day
)

select
    coalesce(role_family, 'all') as role_family,
    coalesce(seniority, 'all') as seniority,
    cast(count(mid_usd) as integer) as postings_with_salary,
    round(quantile_cont(mid_usd, 0.25), 0) as p25_usd,
    round(median(mid_usd), 0) as median_usd,
    round(quantile_cont(mid_usd, 0.75), 0) as p75_usd,
    round(count(mid_usd) / count(*), 4) as share_with_salary
from us
group by grouping sets ((role_family, seniority), (role_family), (seniority), ())
