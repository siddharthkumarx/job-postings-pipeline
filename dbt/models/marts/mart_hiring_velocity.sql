-- Weekly hiring velocity per company: new vs closed postings and new / open ratio.
with weekly as (
    select
        week_start,
        company_id,
        sum(new_roles) as new_postings,
        sum(closed_roles) as closed_postings,
        sum(open_roles) as open_at_week_end
    from {{ ref('mart_weekly_open_roles') }}
    group by 1, 2
)

select
    week_start,
    company_id,
    cast(new_postings as integer) as new_postings,
    cast(closed_postings as integer) as closed_postings,
    cast(new_postings - closed_postings as integer) as net_change,
    cast(open_at_week_end as integer) as open_at_week_end,
    round(new_postings / nullif(open_at_week_end, 0), 4) as velocity
from weekly
