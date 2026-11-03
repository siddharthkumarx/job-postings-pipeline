-- How long closed postings stayed open, by role family (left-censored postings excluded).
with closed as (
    select role_family, days_open
    from {{ ref('fct_job_postings') }}
    where closed_on is not null and not left_censored
),

labelled as (
    select
        role_family,
        days_open,
        case
            when days_open <= 7 then '0-7' when days_open <= 14 then '8-14'
            when days_open <= 30 then '15-30' when days_open <= 60 then '31-60'
            when days_open <= 90 then '61-90' else '91+'
        end as band
    from closed
    union all
    select 'all' as role_family, days_open,
        case
            when days_open <= 7 then '0-7' when days_open <= 14 then '8-14'
            when days_open <= 30 then '15-30' when days_open <= 60 then '31-60'
            when days_open <= 90 then '61-90' else '91+'
        end as band
    from closed
),

bands as (
    select * from (values
        ('0-7', 1), ('8-14', 2), ('15-30', 3), ('31-60', 4), ('61-90', 5), ('91+', 6)
    ) as b (band, band_order)
),

families as (
    select role_family, count(*) as n, median(days_open) as median_days_open
    from labelled
    group by 1
)

select
    f.role_family,
    b.band,
    cast(b.band_order as integer) as band_order,
    cast(count(l.days_open) as integer) as closed_postings,
    round(count(l.days_open) / f.n, 4) as share,
    cast(f.median_days_open as double) as median_days_open
from families as f
cross join bands as b
left join labelled as l on l.role_family = f.role_family and l.band = b.band
group by f.role_family, b.band, b.band_order, f.n, f.median_days_open
