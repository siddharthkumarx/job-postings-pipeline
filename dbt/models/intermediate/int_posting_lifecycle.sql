{#
  Posting lifecycle (docs/decisions.md D-011): first/last seen, closed after missing from
  2 consecutive runs in which its board was fetched OK, reopen count, days open,
  left censoring (already open on the board's first successful fetch).
#}
with daily as (
    select posting_key, company_id, run_date from {{ ref('int_postings_daily') }}
),

board_ok as (
    select company_id, run_date from {{ ref('stg_board_runs') }} where status = 'ok'
),

board_first as (
    select company_id, min(run_date) as first_ok_run from board_ok group by 1
),

latest as (
    select max(run_date) as latest_run from {{ ref('int_run_calendar') }}
),

spans as (
    select
        posting_key,
        any_value(company_id) as company_id,
        min(run_date) as first_seen,
        max(run_date) as last_seen,
        count(*) as runs_listed
    from daily
    group by 1
),

after_last as (
    -- successful fetches of the posting's board after it was last listed
    select
        s.posting_key,
        b.run_date,
        row_number() over (partition by s.posting_key order by b.run_date) as nth_absence
    from spans as s
    inner join board_ok as b on b.company_id = s.company_id and b.run_date > s.last_seen
),

closing as (
    select posting_key, min(run_date) as closed_on
    from after_last
    group by 1
    having max(nth_absence) >= 2
),

inside as (
    -- successful fetches between first and last seen: present or absent?
    select
        s.posting_key,
        b.run_date,
        (d.posting_key is not null) as present
    from spans as s
    inner join board_ok as b
        on b.company_id = s.company_id and b.run_date between s.first_seen and s.last_seen
    left join daily as d on d.posting_key = s.posting_key and d.run_date = b.run_date
),

gaps as (
    select
        posting_key,
        present,
        sum(case when present then 1 else 0 end) over (
            partition by posting_key order by run_date rows unbounded preceding
        ) as island
    from inside
),

reopens as (
    select posting_key, count(*) as reopened_count
    from (
        select posting_key, island
        from gaps
        where not present
        group by 1, 2
        having count(*) >= 2
    )
    group by 1
)

select
    s.posting_key,
    s.company_id,
    s.first_seen,
    s.last_seen,
    s.runs_listed,
    c.closed_on,
    c.closed_on is null as is_open,
    case
        when c.closed_on is not null then datediff('day', s.first_seen, s.last_seen) + 1
        else datediff('day', s.first_seen, l.latest_run) + 1
    end as days_open,
    s.first_seen <= bf.first_ok_run as left_censored,
    coalesce(r.reopened_count, 0) as reopened_count
from spans as s
cross join latest as l
left join closing as c on c.posting_key = s.posting_key
left join board_first as bf on bf.company_id = s.company_id
left join reopens as r on r.posting_key = s.posting_key
