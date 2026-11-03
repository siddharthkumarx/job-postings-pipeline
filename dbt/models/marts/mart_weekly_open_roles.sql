-- Weekly open / new / closed roles by company, role family and location.
with last_run as (
    select week_start, max(run_date) as last_run
    from {{ ref('int_run_calendar') }}
    group by 1
),

open_roles as (
    select
        lr.week_start,
        d.company_id,
        d.role_family,
        coalesce(d.country_code, '') as country_code,
        coalesce(d.state_code, '') as state_code,
        count(*) as open_roles
    from last_run as lr
    inner join {{ ref('int_postings_daily') }} as d on d.run_date = lr.last_run
    group by all
),

new_roles as (
    select
        date_trunc('week', first_seen)::date as week_start,
        company_id,
        role_family,
        coalesce(country_code, '') as country_code,
        coalesce(state_code, '') as state_code,
        count(*) filter (where not left_censored) as new_roles
    from {{ ref('fct_job_postings') }}
    group by all
),

closed_roles as (
    select
        date_trunc('week', closed_on)::date as week_start,
        company_id,
        role_family,
        coalesce(country_code, '') as country_code,
        coalesce(state_code, '') as state_code,
        count(*) as closed_roles
    from {{ ref('fct_job_postings') }}
    where closed_on is not null
    group by all
),

keys as (
    select week_start, company_id, role_family, country_code, state_code from open_roles
    union
    select week_start, company_id, role_family, country_code, state_code from new_roles
    union
    select week_start, company_id, role_family, country_code, state_code from closed_roles
)

select
    k.week_start,
    k.company_id,
    k.role_family,
    k.country_code,
    k.state_code,
    cast(coalesce(o.open_roles, 0) as integer) as open_roles,
    cast(coalesce(n.new_roles, 0) as integer) as new_roles,
    cast(coalesce(c.closed_roles, 0) as integer) as closed_roles
from keys as k
left join open_roles as o using (week_start, company_id, role_family, country_code, state_code)
left join new_roles as n using (week_start, company_id, role_family, country_code, state_code)
left join closed_roles as c using (week_start, company_id, role_family, country_code, state_code)
where k.week_start in (select week_start from last_run)
